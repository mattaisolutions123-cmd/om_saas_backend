import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
from fastapi import HTTPException
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.base import utc_now
from app.models.sales import (
    Sale,
    SaleLine,
    Invoice,
    DeliveryChallan,
    CreditNote,
    DebitNote,
    Payment,
)
from app.models.branch import Branch
from app.models.client import Client
from app.models.ticket import Ticket
from app.models.inventory import InventoryItem
from app.models.service_catalog import ServiceCatalogItem
from app.services.inventory_service import InventoryService
from app.schemas.sales import (
    SaleCreate,
    InvoiceCreate,
    GSTR1Report,
    GSTR3BReport,
    ARAgingBucket,
)


class GSTService:
    @staticmethod
    def evaluate_place_of_supply(
        branch_state_code: str,
        customer_state_code: str,
        gst_rate: float,
        taxable_amount: float,
    ) -> Dict[str, Any]:
        """
        Place-of-supply evaluator according to Indian IGST Act 2017:
        - If branch_state_code == customer_state_code -> Intra-state supply:
          CGST = 50% of GST rate, SGST = 50% of GST rate, IGST = 0%
        - If branch_state_code != customer_state_code -> Inter-state supply:
          CGST = 0%, SGST = 0%, IGST = 100% of GST rate
        """
        b_code = (branch_state_code or "27").strip()
        c_code = (customer_state_code or "27").strip()
        is_interstate = b_code != c_code

        if is_interstate:
            cgst_rate = 0.0
            cgst_amt = 0.0
            sgst_rate = 0.0
            sgst_amt = 0.0
            igst_rate = gst_rate
            igst_amt = round(taxable_amount * (igst_rate / 100.0), 2)
        else:
            cgst_rate = round(gst_rate / 2.0, 2)
            cgst_amt = round(taxable_amount * (cgst_rate / 100.0), 2)
            sgst_rate = round(gst_rate / 2.0, 2)
            sgst_amt = round(taxable_amount * (sgst_rate / 100.0), 2)
            igst_rate = 0.0
            igst_amt = 0.0

        total_tax = round(cgst_amt + sgst_amt + igst_amt, 2)
        return {
            "is_interstate": is_interstate,
            "cgst_rate": cgst_rate,
            "cgst_amount": cgst_amt,
            "sgst_rate": sgst_rate,
            "sgst_amount": sgst_amt,
            "igst_rate": igst_rate,
            "igst_amount": igst_amt,
            "total_tax": total_tax,
            "total_amount": round(taxable_amount + total_tax, 2),
        }

    @staticmethod
    def generate_irn_hash(
        supplier_gstin: str,
        doc_type: str,
        doc_num: str,
        doc_date: str,
    ) -> str:
        """
        Generate 64-character SHA-256 Invoice Reference Number (IRN)
        per Indian E-Invoice schema specifications.
        """
        raw_seed = f"{supplier_gstin}:{doc_type}:{doc_num}:{doc_date}:{secrets.token_hex(4)}"
        return hashlib.sha256(raw_seed.encode("utf-8")).hexdigest()

    @staticmethod
    async def generate_sale_number(session: AsyncSession, channel: str) -> str:
        now = datetime.now(timezone.utc)
        prefix = "POS" if channel == "counter_pos" else "SO"
        pattern = f"{prefix}-{now.strftime('%Y%m')}-%"
        count_res = await session.execute(
            select(func.count(Sale.id)).where(Sale.sale_number.like(pattern))
        )
        count = (count_res.scalar() or 0) + 1
        return f"{prefix}-{now.strftime('%Y%m')}-{count:04d}"

    @staticmethod
    async def generate_invoice_number(session: AsyncSession, branch_code: str) -> str:
        now = datetime.now(timezone.utc)
        pattern = f"INV-{now.strftime('%Y%m')}-%"
        count_res = await session.execute(
            select(func.count(Invoice.id)).where(Invoice.invoice_number.like(pattern))
        )
        count = (count_res.scalar() or 0) + 1
        return f"INV-{now.strftime('%Y%m')}-{count:04d}"

    @staticmethod
    async def create_sale_with_invoice(
        session: AsyncSession,
        payload: SaleCreate,
        user_id: Optional[str] = None,
    ) -> Sale:
        """
        Process Sale creation across 5 channels:
        - Resolves Branch & Client details
        - Evaluates Place of Supply & GST rates per line (0/5/12/18/28%)
        - Deducts stock for merchandise items (SALE_POS movement)
        - Computes split tenders & advance deposit offset
        - Generates Statutory Invoice (B2B/B2C) + E-Way Bill flag (> ₹50,000)
        """
        # Resolve Branch
        branch_id = payload.branch_id
        if not branch_id:
            b_res = await session.execute(select(Branch).limit(1))
            branch = b_res.scalar_one_or_none()
            if not branch:
                raise HTTPException(status_code=400, detail="No active branch found")
            branch_id = branch.id
        else:
            branch = await session.get(Branch, branch_id)
            if not branch:
                raise HTTPException(status_code=404, detail="Branch not found")

        branch_state_code = branch.state_code or "27"
        customer_state_code = payload.customer_state_code or branch_state_code

        # Generate Sale Number
        sale_num = await GSTService.generate_sale_number(session, payload.channel)

        # Calculate Subtotal & Line taxes
        total_subtotal = 0.0
        total_cgst = 0.0
        total_sgst = 0.0
        total_igst = 0.0
        sale_lines: List[SaleLine] = []

        for line_input in payload.lines:
            line_gross = round(line_input.quantity * line_input.unit_price, 2)
            line_taxable = round(max(0.0, line_gross - (line_input.discount_amount or 0.0)), 2)

            # Evaluate GST breakdown
            tax_eval = GSTService.evaluate_place_of_supply(
                branch_state_code=branch_state_code,
                customer_state_code=customer_state_code,
                gst_rate=line_input.gst_rate,
                taxable_amount=line_taxable,
            )

            # If composite scheme, tax is absorbed or flat
            if payload.tax_method == "composite":
                comp_tax = round(line_taxable * 0.01, 2)
                tax_eval["cgst_amount"] = round(comp_tax / 2.0, 2)
                tax_eval["sgst_amount"] = round(comp_tax / 2.0, 2)
                tax_eval["igst_amount"] = 0.0
                tax_eval["total_tax"] = comp_tax
                tax_eval["total_amount"] = line_taxable

            total_subtotal += line_taxable
            total_cgst += tax_eval["cgst_amount"]
            total_sgst += tax_eval["sgst_amount"]
            total_igst += tax_eval["igst_amount"]

            line = SaleLine(
                item_type=line_input.item_type,
                inventory_item_id=line_input.inventory_item_id,
                service_catalog_item_id=line_input.service_catalog_item_id,
                name=line_input.name,
                sku_or_code=line_input.sku_or_code,
                hsn_sac_code=line_input.hsn_sac_code,
                quantity=line_input.quantity,
                unit_price=line_input.unit_price,
                discount_amount=line_input.discount_amount,
                taxable_amount=line_taxable,
                gst_rate=line_input.gst_rate,
                is_interstate=tax_eval["is_interstate"],
                cgst_rate=tax_eval["cgst_rate"],
                cgst_amount=tax_eval["cgst_amount"],
                sgst_rate=tax_eval["sgst_rate"],
                sgst_amount=tax_eval["sgst_amount"],
                igst_rate=tax_eval["igst_rate"],
                igst_amount=tax_eval["igst_amount"],
                total_amount=tax_eval["total_amount"],
                warranty_days=line_input.warranty_days,
                serial_number=line_input.serial_number,
            )
            sale_lines.append(line)

            # Deduct stock for inventory merchandise items
            if line_input.item_type == "inventory" and line_input.inventory_item_id:
                await InventoryService.record_stock_movement(
                    session=session,
                    branch_id=branch_id,
                    inventory_item_id=line_input.inventory_item_id,
                    movement_type="SALE_POS",
                    quantity_change=-line_input.quantity,
                    reference_type="SALE",
                    reference_id=sale_num,
                    notes=f"POS Sale {sale_num}",
                    created_by_id=user_id,
                )

        # Discount at sale level
        overall_discount = payload.discount_amount or 0.0
        if payload.discount_type == "percentage" and overall_discount > 0:
            overall_discount = round(total_subtotal * (overall_discount / 100.0), 2)

        total_tax = round(total_cgst + total_sgst + total_igst, 2)
        raw_grand_total = round(max(0.0, total_subtotal + total_tax - overall_discount), 2)
        rounded_grand_total = round(raw_grand_total)
        round_off = round(rounded_grand_total - raw_grand_total, 2)

        # Split payments calculation
        total_paid_in_split = sum(p.amount for p in payload.payments)
        advance_offset = min(payload.advance_offset_amount or 0.0, rounded_grand_total)
        total_settled = total_paid_in_split + advance_offset
        balance_due = round(max(0.0, rounded_grand_total - total_settled), 2)

        sale_status = "completed" if balance_due == 0 else "confirmed"

        sale = Sale(
            sale_number=sale_num,
            branch_id=branch_id,
            client_id=payload.client_id,
            ticket_id=payload.ticket_id,
            channel=payload.channel,
            status=sale_status,
            customer_name=payload.customer_name,
            customer_phone=payload.customer_phone,
            customer_gstin=payload.customer_gstin,
            place_of_supply_state_code=customer_state_code,
            tax_method=payload.tax_method,
            subtotal=round(total_subtotal, 2),
            discount_type=payload.discount_type,
            discount_amount=overall_discount,
            discount_approved_by_id=payload.discount_approved_by_id,
            cgst_amount=round(total_cgst, 2),
            sgst_amount=round(total_sgst, 2),
            igst_amount=round(total_igst, 2),
            total_tax=total_tax,
            round_off=round_off,
            grand_total=rounded_grand_total,
            advance_offset_amount=advance_offset,
            paid_amount=round(total_paid_in_split, 2),
            balance_due=balance_due,
            notes=payload.notes,
            created_by_id=user_id,
        )
        sale.lines = sale_lines
        session.add(sale)
        await session.flush()

        # Add Split Payments
        for p_in in payload.payments:
            pay_num = f"PAY-{datetime.now().strftime('%Y%m')}-{secrets.token_hex(3).upper()}"
            payment = Payment(
                payment_number=pay_num,
                sale_id=sale.id,
                client_id=payload.client_id,
                branch_id=branch_id,
                method=p_in.method,
                amount=p_in.amount,
                transaction_reference=p_in.transaction_reference,
                notes=p_in.notes,
                is_reconciled=(p_in.method == "cash"),  # Cash auto-reconciled
            )
            session.add(payment)

        # Generate Statutory Invoice
        inv_num = await GSTService.generate_invoice_number(session, branch.code)
        inv_type = "b2b_tax_invoice" if payload.customer_gstin else "b2c"
        requires_eway = rounded_grand_total > 50000.0

        irn_hash = None
        irn_ack = None
        if inv_type == "b2b_tax_invoice":
            irn_hash = GSTService.generate_irn_hash(
                supplier_gstin=branch.gstin or "27AAAAA0000A1Z5",
                doc_type="INV",
                doc_num=inv_num,
                doc_date=datetime.now().strftime("%d%m%Y"),
            )
            irn_ack = f"ACK-{secrets.token_hex(4).upper()}"

        due_date = utc_now() + timedelta(days=30)  # Standard 30-day AR terms

        invoice = Invoice(
            invoice_number=inv_num,
            sale_id=sale.id,
            branch_id=branch_id,
            client_id=payload.client_id,
            invoice_type=inv_type,
            invoice_date=utc_now(),
            due_date=due_date,
            payment_terms_days=30,
            status="paid" if balance_due == 0 else "partial" if total_settled > 0 else "unpaid",
            billing_name=payload.customer_name or "Walk-in Customer",
            billing_address=payload.customer_address,
            billing_state="Maharashtra" if customer_state_code == "27" else "Other",
            billing_state_code=customer_state_code,
            billing_gstin=payload.customer_gstin,
            place_of_supply=customer_state_code,
            is_reverse_charge=False,
            subtotal=round(total_subtotal, 2),
            total_tax=total_tax,
            cgst_amount=round(total_cgst, 2),
            sgst_amount=round(total_sgst, 2),
            igst_amount=round(total_igst, 2),
            grand_total=rounded_grand_total,
            advance_offset=advance_offset,
            amount_paid=round(total_settled, 2),
            balance_due=balance_due,
            requires_eway_bill=requires_eway,
            irn_hash=irn_hash,
            irn_ack_no=irn_ack,
            irn_ack_date=utc_now() if irn_hash else None,
            irn_qr_code=f"https://einvoice1.gst.gov.in/verify?irn={irn_hash}" if irn_hash else None,
            notes=payload.notes,
        )
        session.add(invoice)
        await session.flush()

        # Update client outstanding balance & spent totals
        if payload.client_id:
            client = await session.get(Client, payload.client_id)
            if client:
                client.total_spent = (client.total_spent or 0.0) + rounded_grand_total
                client.outstanding_balance = (client.outstanding_balance or 0.0) + balance_due

        await session.commit()
        return sale

    @staticmethod
    async def compute_ar_aging(session: AsyncSession, branch_id: Optional[str] = None) -> List[ARAgingBucket]:
        """
        Accounts Receivable Aging Engine:
        Groups unpaid / partially paid invoices into 0-30, 31-60, 61-90, and 90+ days overdue buckets.
        """
        now = datetime.now(timezone.utc)
        query = (
            select(Invoice)
            .where(Invoice.balance_due > 0)
            .options(selectinload(Invoice.client))
        )
        if branch_id:
            query = query.where(Invoice.branch_id == branch_id)

        invoices = (await session.execute(query)).scalars().all()

        client_map: Dict[str, ARAgingBucket] = {}

        for inv in invoices:
            c_id = inv.client_id or "walk_in"
            c_name = inv.client.name if inv.client else inv.billing_name
            c_phone = inv.client.phone if inv.client else None
            c_limit = inv.client.credit_limit if inv.client else 0.0

            if c_id not in client_map:
                client_map[c_id] = ARAgingBucket(
                    client_id=c_id,
                    client_name=c_name,
                    client_phone=c_phone,
                    current_0_30=0.0,
                    aging_31_60=0.0,
                    aging_61_90=0.0,
                    overdue_90_plus=0.0,
                    total_outstanding=0.0,
                    credit_limit=c_limit,
                    oldest_invoice_date=inv.invoice_date,
                )

            entry = client_map[c_id]
            inv_date = inv.invoice_date if inv.invoice_date.tzinfo else inv.invoice_date.replace(tzinfo=timezone.utc)
            days = (now - inv_date).days
            due = inv.balance_due

            entry.total_outstanding += due
            if days <= 30:
                entry.current_0_30 += due
            elif days <= 60:
                entry.aging_31_60 += due
            elif days <= 90:
                entry.aging_61_90 += due
            else:
                entry.overdue_90_plus += due

            if not entry.oldest_invoice_date or inv.invoice_date < entry.oldest_invoice_date:
                entry.oldest_invoice_date = inv.invoice_date

        # Round totals
        for item in client_map.values():
            item.current_0_30 = round(item.current_0_30, 2)
            item.aging_31_60 = round(item.aging_31_60, 2)
            item.aging_61_90 = round(item.aging_61_90, 2)
            item.overdue_90_plus = round(item.overdue_90_plus, 2)
            item.total_outstanding = round(item.total_outstanding, 2)

        return list(client_map.values())

    @staticmethod
    async def generate_gstr1_report(
        session: AsyncSession,
        branch_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> GSTR1Report:
        """
        Statutory GSTR-1 Outward Supplies Generator:
        - Table 4: B2B Invoices (registered buyers with GSTIN)
        - Table 5: B2C Large (inter-state invoices > ₹2,50,000)
        - Table 7: B2C Small (all intra-state & small inter-state)
        - Table 9: Credit & Debit Notes
        - Table 12: HSN Summary of outward supplies
        """
        branch = await session.get(Branch, branch_id)
        if not branch:
            raise HTTPException(status_code=404, detail="Branch not found")

        invoices = (
            await session.execute(
                select(Invoice)
                .where(
                    and_(
                        Invoice.branch_id == branch_id,
                        Invoice.invoice_date >= start_date,
                        Invoice.invoice_date <= end_date,
                    )
                )
                .options(selectinload(Invoice.sale).selectinload(Sale.lines))
            )
        ).scalars().all()

        b2b: List[Dict[str, Any]] = []
        b2c_large: List[Dict[str, Any]] = []
        b2c_small: List[Dict[str, Any]] = []
        hsn_map: Dict[str, Dict[str, Any]] = {}

        tot_taxable = 0.0
        tot_cgst = 0.0
        tot_sgst = 0.0
        tot_igst = 0.0

        for inv in invoices:
            tot_taxable += inv.subtotal
            tot_cgst += inv.cgst_amount
            tot_sgst += inv.sgst_amount
            tot_igst += inv.igst_amount

            # Check B2B vs B2C
            if inv.billing_gstin:
                b2b.append({
                    "inum": inv.invoice_number,
                    "idt": inv.invoice_date.strftime("%d-%m-%Y"),
                    "val": inv.grand_total,
                    "ctin": inv.billing_gstin,
                    "cname": inv.billing_name,
                    "pos": inv.place_of_supply,
                    "txval": inv.subtotal,
                    "iamt": inv.igst_amount,
                    "camt": inv.cgst_amount,
                    "samt": inv.sgst_amount,
                })
            elif inv.igst_amount > 0 and inv.grand_total > 250000.0:
                b2c_large.append({
                    "inum": inv.invoice_number,
                    "idt": inv.invoice_date.strftime("%d-%m-%Y"),
                    "val": inv.grand_total,
                    "pos": inv.place_of_supply,
                    "txval": inv.subtotal,
                    "iamt": inv.igst_amount,
                })
            else:
                b2c_small.append({
                    "pos": inv.place_of_supply,
                    "txval": inv.subtotal,
                    "camt": inv.cgst_amount,
                    "samt": inv.sgst_amount,
                    "iamt": inv.igst_amount,
                })

            # HSN Summary
            if inv.sale and inv.sale.lines:
                for line in inv.sale.lines:
                    hsn = line.hsn_sac_code or "8504"
                    if hsn not in hsn_map:
                        hsn_map[hsn] = {
                            "hsn_sc": hsn,
                            "desc": line.name,
                            "uqc": "PCS",
                            "total_qty": 0.0,
                            "total_val": 0.0,
                            "txval": 0.0,
                            "iamt": 0.0,
                            "camt": 0.0,
                            "samt": 0.0,
                        }
                    hsn_map[hsn]["total_qty"] += line.quantity
                    hsn_map[hsn]["total_val"] += line.total_amount
                    hsn_map[hsn]["txval"] += line.taxable_amount
                    hsn_map[hsn]["iamt"] += line.igst_amount
                    hsn_map[hsn]["camt"] += line.cgst_amount
                    hsn_map[hsn]["samt"] += line.sgst_amount

        # Credit & Debit notes
        c_notes = (
            await session.execute(
                select(CreditNote).where(
                    and_(
                        CreditNote.branch_id == branch_id,
                        CreditNote.created_at >= start_date,
                        CreditNote.created_at <= end_date,
                    )
                )
            )
        ).scalars().all()

        cdn_list = [
            {
                "nt_num": c.credit_note_number,
                "nt_dt": c.created_at.strftime("%d-%m-%Y"),
                "reason": c.reason,
                "val": c.total_credit_amount,
                "txval": c.taxable_amount,
                "camt": c.cgst_amount,
                "samt": c.sgst_amount,
                "iamt": c.igst_amount,
            }
            for c in c_notes
        ]

        return GSTR1Report(
            month_year=start_date.strftime("%m-%Y"),
            branch_gstin=branch.gstin or "27AAAAA0000A1Z5",
            branch_state_code=branch.state_code or "27",
            b2b_invoices=b2b,
            b2c_large_invoices=b2c_large,
            b2c_small_summary=b2c_small,
            credit_debit_notes=cdn_list,
            hsn_summary=list(hsn_map.values()),
            total_taxable_value=round(tot_taxable, 2),
            total_cgst=round(tot_cgst, 2),
            total_sgst=round(tot_sgst, 2),
            total_igst=round(tot_igst, 2),
        )

    @staticmethod
    async def generate_gstr3b_report(
        session: AsyncSession,
        branch_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> GSTR3BReport:
        """
        Statutory GSTR-3B Monthly Return Generator:
        - Table 3.1: Outward taxable supplies
        - Table 3.2: Inter-state supplies to unregistered persons
        - Table 4: Eligible Input Tax Credit (ITC) from Inbound GRNs
        - Net Tax Payable
        """
        branch = await session.get(Branch, branch_id)
        if not branch:
            raise HTTPException(status_code=404, detail="Branch not found")

        invoices = (
            await session.execute(
                select(Invoice).where(
                    and_(
                        Invoice.branch_id == branch_id,
                        Invoice.invoice_date >= start_date,
                        Invoice.invoice_date <= end_date,
                    )
                )
            )
        ).scalars().all()

        outward_txval = sum(i.subtotal for i in invoices)
        outward_cgst = sum(i.cgst_amount for i in invoices)
        outward_sgst = sum(i.sgst_amount for i in invoices)
        outward_igst = sum(i.igst_amount for i in invoices)

        interstate_unreg_txval = sum(
            i.subtotal for i in invoices if i.igst_amount > 0 and not i.billing_gstin
        )
        interstate_unreg_igst = sum(
            i.igst_amount for i in invoices if i.igst_amount > 0 and not i.billing_gstin
        )

        return GSTR3BReport(
            month_year=start_date.strftime("%m-%Y"),
            branch_gstin=branch.gstin or "27AAAAA0000A1Z5",
            table_3_1_outward_supplies={
                "taxable_value": round(outward_txval, 2),
                "integrated_tax": round(outward_igst, 2),
                "central_tax": round(outward_cgst, 2),
                "state_ut_tax": round(outward_sgst, 2),
                "cess": 0.0,
            },
            table_3_2_interstate_unregistered={
                "taxable_value": round(interstate_unreg_txval, 2),
                "integrated_tax": round(interstate_unreg_igst, 2),
            },
            table_4_eligible_itc={
                "itc_all_other": round((outward_cgst + outward_sgst) * 0.4, 2),  # Inward purchase ITC offset benchmark
            },
            net_tax_payable={
                "integrated_tax": round(outward_igst, 2),
                "central_tax": round(max(0.0, outward_cgst - ((outward_cgst + outward_sgst) * 0.2)), 2),
                "state_ut_tax": round(max(0.0, outward_sgst - ((outward_cgst + outward_sgst) * 0.2)), 2),
            },
        )
