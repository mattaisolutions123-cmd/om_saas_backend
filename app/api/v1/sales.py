import secrets
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, desc
from sqlalchemy.orm import selectinload

from app.db.session import get_db
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
from app.schemas.sales import (
    SaleCreate,
    SaleResponse,
    SaleLineResponse,
    InvoiceCreate,
    InvoiceResponse,
    DeliveryChallanCreate,
    DeliveryChallanResponse,
    CreditNoteCreate,
    CreditNoteResponse,
    DebitNoteCreate,
    DebitNoteResponse,
    PaymentResponse,
    PaymentReconcilePayload,
    ARAgingBucket,
    GSTR1Report,
    GSTR3BReport,
)
from app.services.gst_service import GSTService
from app.services.audit import log_audit_event
from app.models.base import utc_now

router = APIRouter(prefix="/sales", tags=["Sales, POS & GST Billing"])


def _serialize_sale(s: Sale) -> Dict[str, Any]:
    client_name = s.client.name if s.client else s.customer_name
    branch_name = s.branch.name if s.branch else None
    first_invoice = s.invoices[0] if s.invoices else None

    lines_data = [
        {
            "id": l.id,
            "sale_id": l.sale_id,
            "item_type": l.item_type,
            "inventory_item_id": l.inventory_item_id,
            "service_catalog_item_id": l.service_catalog_item_id,
            "name": l.name,
            "sku_or_code": l.sku_or_code,
            "hsn_sac_code": l.hsn_sac_code,
            "quantity": l.quantity,
            "unit_price": l.unit_price,
            "discount_amount": l.discount_amount,
            "taxable_amount": l.taxable_amount,
            "gst_rate": l.gst_rate,
            "is_interstate": l.is_interstate,
            "cgst_rate": l.cgst_rate,
            "cgst_amount": l.cgst_amount,
            "sgst_rate": l.sgst_rate,
            "sgst_amount": l.sgst_amount,
            "igst_rate": l.igst_rate,
            "igst_amount": l.igst_amount,
            "total_amount": l.total_amount,
            "warranty_days": l.warranty_days,
            "serial_number": l.serial_number,
        }
        for l in s.lines
    ]

    payments_data = [
        {
            "id": p.id,
            "payment_number": p.payment_number,
            "sale_id": p.sale_id,
            "invoice_id": p.invoice_id,
            "client_id": p.client_id,
            "branch_id": p.branch_id,
            "method": p.method,
            "amount": p.amount,
            "transaction_reference": p.transaction_reference,
            "payment_date": p.payment_date,
            "is_reconciled": p.is_reconciled,
            "reconciled_at": p.reconciled_at,
            "reconciled_by_id": p.reconciled_by_id,
            "bank_statement_reference": p.bank_statement_reference,
            "notes": p.notes,
            "created_at": p.created_at,
        }
        for p in s.payments
    ]

    return {
        "id": s.id,
        "sale_number": s.sale_number,
        "branch_id": s.branch_id,
        "client_id": s.client_id,
        "ticket_id": s.ticket_id,
        "channel": s.channel,
        "status": s.status,
        "customer_name": s.customer_name,
        "customer_phone": s.customer_phone,
        "customer_gstin": s.customer_gstin,
        "place_of_supply_state_code": s.place_of_supply_state_code,
        "tax_method": s.tax_method,
        "subtotal": s.subtotal,
        "discount_type": s.discount_type,
        "discount_amount": s.discount_amount,
        "discount_approved_by_id": s.discount_approved_by_id,
        "cgst_amount": s.cgst_amount,
        "sgst_amount": s.sgst_amount,
        "igst_amount": s.igst_amount,
        "total_tax": s.total_tax,
        "round_off": s.round_off,
        "grand_total": s.grand_total,
        "advance_offset_amount": s.advance_offset_amount,
        "paid_amount": s.paid_amount,
        "balance_due": s.balance_due,
        "notes": s.notes,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
        "client_name": client_name,
        "branch_name": branch_name,
        "invoice_id": first_invoice.id if first_invoice else None,
        "invoice_number": first_invoice.invoice_number if first_invoice else None,
        "lines": lines_data,
        "payments": payments_data,
    }


# 1. Create Sale (POS Checkout / Invoicing)
@router.post("", response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
async def create_sale(
    payload: SaleCreate,
    db: AsyncSession = Depends(get_db),
):
    sale = await GSTService.create_sale_with_invoice(session=db, payload=payload)

    # Reload with all relations
    query = (
        select(Sale)
        .where(Sale.id == sale.id)
        .options(
            selectinload(Sale.lines),
            selectinload(Sale.payments),
            selectinload(Sale.invoices),
            selectinload(Sale.client),
            selectinload(Sale.branch),
        )
    )
    reloaded = (await db.execute(query)).scalar_one()
    return _serialize_sale(reloaded)


# 2. List Sales
@router.get("", response_model=List[SaleResponse])
async def list_sales(
    channel: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    branch_id: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Sale)
        .options(
            selectinload(Sale.lines),
            selectinload(Sale.payments),
            selectinload(Sale.invoices),
            selectinload(Sale.client),
            selectinload(Sale.branch),
        )
        .order_by(Sale.created_at.desc())
    )

    if channel:
        query = query.where(Sale.channel == channel)
    if status:
        query = query.where(Sale.status == status)
    if branch_id:
        query = query.where(Sale.branch_id == branch_id)
    if client_id:
        query = query.where(Sale.client_id == client_id)
    if search:
        search_filter = or_(
            Sale.sale_number.ilike(f"%{search}%"),
            Sale.customer_name.ilike(f"%{search}%"),
            Sale.customer_phone.ilike(f"%{search}%"),
            Sale.customer_gstin.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)

    sales = (await db.execute(query)).scalars().all()
    return [_serialize_sale(s) for s in sales]


# 4. List Invoices
@router.get("/invoices/all", response_model=List[InvoiceResponse])
async def list_invoices(
    invoice_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    branch_id: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(Invoice).order_by(Invoice.invoice_date.desc())

    if invoice_type:
        query = query.where(Invoice.invoice_type == invoice_type)
    if status:
        query = query.where(Invoice.status == status)
    if branch_id:
        query = query.where(Invoice.branch_id == branch_id)
    if client_id:
        query = query.where(Invoice.client_id == client_id)
    if search:
        search_filter = or_(
            Invoice.invoice_number.ilike(f"%{search}%"),
            Invoice.billing_name.ilike(f"%{search}%"),
            Invoice.billing_gstin.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)

    invoices = (await db.execute(query)).scalars().all()
    return [InvoiceResponse.model_validate(inv) for inv in invoices]


# 5. Get Invoice Detail
@router.get("/invoices/{id}", response_model=InvoiceResponse)
async def get_invoice(
    id: str,
    db: AsyncSession = Depends(get_db),
):
    inv = await db.get(Invoice, id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return InvoiceResponse.model_validate(inv)


# 6. Delivery Challans
@router.post("/challans", response_model=DeliveryChallanResponse, status_code=status.HTTP_201_CREATED)
async def create_delivery_challan(
    payload: DeliveryChallanCreate,
    db: AsyncSession = Depends(get_db),
):
    # Resolve Branch
    branch_res = await db.execute(select(Branch).limit(1))
    branch = branch_res.scalar_one_or_none()
    branch_id = branch.id if branch else "default_branch"

    now = datetime.now(timezone.utc)
    ch_num = f"DC-{now.strftime('%Y%m')}-{secrets.token_hex(3).upper()}"

    challan = DeliveryChallan(
        challan_number=ch_num,
        sale_id=payload.sale_id,
        branch_id=branch_id,
        client_id=payload.client_id,
        challan_type=payload.challan_type,
        transporter_name=payload.transporter_name,
        vehicle_number=payload.vehicle_number,
        eway_bill_number=payload.eway_bill_number,
        status="dispatched",
        items=payload.items,
        notes=payload.notes,
    )
    db.add(challan)
    await db.commit()
    await db.refresh(challan)
    return DeliveryChallanResponse.model_validate(challan)


@router.get("/challans", response_model=List[DeliveryChallanResponse])
async def list_delivery_challans(
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(DeliveryChallan).order_by(DeliveryChallan.created_at.desc())
    if branch_id:
        query = query.where(DeliveryChallan.branch_id == branch_id)
    challans = (await db.execute(query)).scalars().all()
    return [DeliveryChallanResponse.model_validate(c) for c in challans]


# 7. Credit Notes
@router.post("/credit-notes", response_model=CreditNoteResponse, status_code=status.HTTP_201_CREATED)
async def create_credit_note(
    payload: CreditNoteCreate,
    db: AsyncSession = Depends(get_db),
):
    inv = await db.get(Invoice, payload.invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    now = datetime.now(timezone.utc)
    cn_num = f"CN-{now.strftime('%Y%m')}-{secrets.token_hex(3).upper()}"
    total_tax = payload.cgst_amount + payload.sgst_amount + payload.igst_amount
    total_amt = round(payload.taxable_amount + total_tax, 2)

    cn = CreditNote(
        credit_note_number=cn_num,
        invoice_id=inv.id,
        branch_id=inv.branch_id,
        client_id=inv.client_id,
        reason=payload.reason,
        taxable_amount=payload.taxable_amount,
        cgst_amount=payload.cgst_amount,
        sgst_amount=payload.sgst_amount,
        igst_amount=payload.igst_amount,
        total_credit_amount=total_amt,
        notes=payload.notes,
    )
    db.add(cn)

    # Adjust invoice balance
    inv.balance_due = max(0.0, inv.balance_due - total_amt)
    await db.commit()
    await db.refresh(cn)
    return CreditNoteResponse.model_validate(cn)


@router.get("/credit-notes", response_model=List[CreditNoteResponse])
async def list_credit_notes(
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(CreditNote).order_by(CreditNote.created_at.desc())
    if branch_id:
        query = query.where(CreditNote.branch_id == branch_id)
    notes = (await db.execute(query)).scalars().all()
    return [CreditNoteResponse.model_validate(n) for n in notes]


# 8. Debit Notes
@router.post("/debit-notes", response_model=DebitNoteResponse, status_code=status.HTTP_201_CREATED)
async def create_debit_note(
    payload: DebitNoteCreate,
    db: AsyncSession = Depends(get_db),
):
    inv = await db.get(Invoice, payload.invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    now = datetime.now(timezone.utc)
    dn_num = f"DN-{now.strftime('%Y%m')}-{secrets.token_hex(3).upper()}"
    total_tax = payload.cgst_amount + payload.sgst_amount + payload.igst_amount
    total_amt = round(payload.taxable_amount + total_tax, 2)

    dn = DebitNote(
        debit_note_number=dn_num,
        invoice_id=inv.id,
        branch_id=inv.branch_id,
        client_id=inv.client_id,
        reason=payload.reason,
        taxable_amount=payload.taxable_amount,
        cgst_amount=payload.cgst_amount,
        sgst_amount=payload.sgst_amount,
        igst_amount=payload.igst_amount,
        total_debit_amount=total_amt,
        notes=payload.notes,
    )
    db.add(dn)

    # Increase invoice balance
    inv.balance_due = round(inv.balance_due + total_amt, 2)
    inv.grand_total = round(inv.grand_total + total_amt, 2)
    await db.commit()
    await db.refresh(dn)
    return DebitNoteResponse.model_validate(dn)


@router.get("/debit-notes", response_model=List[DebitNoteResponse])
async def list_debit_notes(
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(DebitNote).order_by(DebitNote.created_at.desc())
    if branch_id:
        query = query.where(DebitNote.branch_id == branch_id)
    notes = (await db.execute(query)).scalars().all()
    return [DebitNoteResponse.model_validate(n) for n in notes]


# 9. Accounts Receivable (AR) Aging Table
@router.get("/ar-aging", response_model=List[ARAgingBucket])
async def get_ar_aging(
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await GSTService.compute_ar_aging(session=db, branch_id=branch_id)


# 10. Bank Reconciliation for NEFT / RTGS
@router.post("/payments/{payment_id}/reconcile", response_model=PaymentResponse)
async def reconcile_payment(
    payment_id: str,
    payload: PaymentReconcilePayload,
    db: AsyncSession = Depends(get_db),
):
    payment = await db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment record not found")

    payment.is_reconciled = True
    payment.reconciled_at = utc_now()
    payment.bank_statement_reference = payload.bank_statement_reference
    if payload.notes:
        payment.notes = f"{payment.notes or ''}\nRecon: {payload.notes}".strip()

    await db.commit()
    await db.refresh(payment)
    return PaymentResponse.model_validate(payment)


# 11. GSTR-1 Statutory Report Generator
@router.get("/reports/gstr1", response_model=GSTR1Report)
async def get_gstr1_report(
    branch_id: Optional[str] = Query(None),
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2030),
    db: AsyncSession = Depends(get_db),
):
    if not branch_id:
        b_res = await db.execute(select(Branch).limit(1))
        branch = b_res.scalar_one_or_none()
        if not branch:
            raise HTTPException(status_code=400, detail="No active branch found")
        branch_id = branch.id

    start_date = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
    if month == 12:
        end_date = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    else:
        end_date = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    return await GSTService.generate_gstr1_report(
        session=db,
        branch_id=branch_id,
        start_date=start_date,
        end_date=end_date,
    )


# 12. GSTR-3B Statutory Report Generator
@router.get("/reports/gstr3b", response_model=GSTR3BReport)
async def get_gstr3b_report(
    branch_id: Optional[str] = Query(None),
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2030),
    db: AsyncSession = Depends(get_db),
):
    if not branch_id:
        b_res = await db.execute(select(Branch).limit(1))
        branch = b_res.scalar_one_or_none()
        if not branch:
            raise HTTPException(status_code=400, detail="No active branch found")
        branch_id = branch.id

    start_date = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
    if month == 12:
        end_date = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    else:
        end_date = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    return await GSTService.generate_gstr3b_report(
        session=db,
        branch_id=branch_id,
        start_date=start_date,
        end_date=end_date,
    )


# 13. Get Sale Detail by ID (Must be after specific routes)
@router.get("/{id}", response_model=SaleResponse)
async def get_sale(
    id: str,
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Sale)
        .where(Sale.id == id)
        .options(
            selectinload(Sale.lines),
            selectinload(Sale.payments),
            selectinload(Sale.invoices),
            selectinload(Sale.client),
            selectinload(Sale.branch),
        )
    )
    sale = (await db.execute(query)).scalar_one_or_none()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale record not found")
    return _serialize_sale(sale)
