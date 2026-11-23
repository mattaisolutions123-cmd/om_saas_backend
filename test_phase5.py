import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.session import AsyncSessionLocal
from app.models.branch import Branch
from app.models.client import Client
from app.models.inventory import InventoryItem
from app.services.inventory_service import InventoryService
from sqlalchemy import select
import secrets


async def run_phase5_tests():
    print("==================================================")
    print("🚀 STARTING PHASE 5 SALES, POS & GST ENGINE SUITE")
    print("==================================================")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Step 0: Base test data setup
        async with AsyncSessionLocal() as db:
            # Check or create branch
            b_res = await db.execute(select(Branch).limit(1))
            branch = b_res.scalar_one_or_none()
            if not branch:
                branch = Branch(
                    name="OmniSuite Mumbai Flagship",
                    code="BR-MUM-POS",
                    state_code="27",
                    gstin="27AABCU9603R1ZM",
                    currency="INR",
                )
                db.add(branch)
                await db.flush()

            # Create test client
            test_client = Client(
                name="TechCorp India Pvt Ltd",
                phone="9821098210",
                email="finance@techcorp.in",
                client_type="corporate",
                gstin="29ABCDE1234F1Z5",  # Karnataka GSTIN (Inter-state supply)
                branch_id=branch.id,
                credit_limit=150000.0,
            )
            db.add(test_client)
            await db.flush()

            # Create inventory items with initial stock
            rand = secrets.token_hex(3)
            item1 = InventoryItem(
                branch_id=branch.id,
                name=f"MacBook Air M2 Retina Display {rand}",
                sku=f"SP-MBA-M2-{rand}",
                barcode=f"BC-POS-{rand}-1",
                cost_price=18000.0,
                retail_price=28000.0,
                tax_rate=18.0,
                hsn_code="8471",
            )
            item2 = InventoryItem(
                branch_id=branch.id,
                name=f"GaN 100W Fast Charger {rand}",
                sku=f"ACC-GAN-100W-{rand}",
                barcode=f"BC-POS-{rand}-2",
                cost_price=1200.0,
                retail_price=2999.0,
                tax_rate=18.0,
                hsn_code="8504",
            )
            db.add_all([item1, item2])
            await db.flush()

            # Add initial stock
            await InventoryService.record_stock_movement(
                session=db,
                branch_id=branch.id,
                inventory_item_id=item1.id,
                movement_type="PURCHASE_GRN",
                quantity_change=10.0,
                unit_cost=18000.0,
                reference_type="INIT",
            )
            await InventoryService.record_stock_movement(
                session=db,
                branch_id=branch.id,
                inventory_item_id=item2.id,
                movement_type="PURCHASE_GRN",
                quantity_change=25.0,
                unit_cost=1200.0,
                reference_type="INIT",
            )
            await db.commit()

            branch_id = branch.id
            client_id = test_client.id
            item1_id = item1.id
            item2_id = item2.id

        # TEST 1: Intra-state Walk-in Counter POS Sale (MH to MH -> CGST 9% + SGST 9%)
        print("\n--- Test 1: Intra-State Counter POS Checkout (CGST + SGST) ---")
        pos_payload = {
            "branch_id": branch_id,
            "channel": "counter_pos",
            "customer_name": "Walk-in Customer",
            "customer_phone": "9820011223",
            "customer_state_code": "27",  # Intra-state Maharashtra
            "tax_method": "line_item",
            "lines": [
                {
                    "item_type": "inventory",
                    "inventory_item_id": item2_id,
                    "name": "GaN 100W Fast Charger",
                    "hsn_sac_code": "8504",
                    "quantity": 2.0,
                    "unit_price": 2999.0,
                    "gst_rate": 18.0,
                }
            ],
            "payments": [
                {"method": "cash", "amount": 3000.0},
                {"method": "upi", "amount": 4078.0, "transaction_reference": "UPI/4129881290"},
            ],
        }
        res1 = await client.post("/api/v1/sales", json=pos_payload)
        assert res1.status_code == 201, f"POS sale failed: {res1.text}"
        sale1 = res1.json()
        print(f"✅ Sale created: {sale1['sale_number']} (Channel: {sale1['channel']})")
        print(f"Subtotal: ₹{sale1['subtotal']:.2f}")
        print(f"CGST (9%): ₹{sale1['cgst_amount']:.2f} | SGST (9%): ₹{sale1['sgst_amount']:.2f} | IGST: ₹{sale1['igst_amount']:.2f}")
        print(f"Grand Total: ₹{sale1['grand_total']:.2f} | Balance Due: ₹{sale1['balance_due']:.2f}")
        assert sale1["cgst_amount"] > 0 and sale1["sgst_amount"] > 0, "Intra-state should have CGST & SGST"
        assert sale1["igst_amount"] == 0.0, "Intra-state should have 0 IGST"
        assert sale1["balance_due"] == 0.0, "Full split payment should settle balance"

        # TEST 2: Inter-state Corporate B2B Tax Invoice (MH to KA -> IGST 18% & IRN)
        print("\n--- Test 2: Inter-State Corporate B2B Tax Invoice (IGST + IRN) ---")
        b2b_payload = {
            "branch_id": branch_id,
            "client_id": client_id,
            "channel": "b2b_contract",
            "customer_name": "TechCorp India Pvt Ltd",
            "customer_phone": "9821098210",
            "customer_gstin": "29ABCDE1234F1Z5",
            "customer_state_code": "29",  # Karnataka (Inter-state)
            "customer_address": "Prestige Tech Park, Bangalore 560103",
            "lines": [
                {
                    "item_type": "inventory",
                    "inventory_item_id": item1_id,
                    "name": "MacBook Air M2 Retina Display",
                    "hsn_sac_code": "8471",
                    "quantity": 2.0,
                    "unit_price": 28000.0,
                    "gst_rate": 18.0,
                }
            ],
            "payments": [],  # On 30-day AR terms
        }
        res2 = await client.post("/api/v1/sales", json=b2b_payload)
        assert res2.status_code == 201, f"B2B sale failed: {res2.text}"
        sale2 = res2.json()
        print(f"✅ B2B Sale created: {sale2['sale_number']}")
        print(f"Subtotal: ₹{sale2['subtotal']:.2f} | IGST (18%): ₹{sale2['igst_amount']:.2f}")
        print(f"Grand Total: ₹{sale2['grand_total']:.2f} | Unpaid AR Balance: ₹{sale2['balance_due']:.2f}")
        assert sale2["igst_amount"] > 0, "Inter-state should charge IGST"
        assert sale2["cgst_amount"] == 0.0 and sale2["sgst_amount"] == 0.0, "Inter-state should have 0 CGST/SGST"

        # Check statutory invoice & IRN generated
        inv_id = sale2["invoice_id"]
        inv_res = await client.get(f"/api/v1/sales/invoices/{inv_id}")
        assert inv_res.status_code == 200
        inv_data = inv_res.json()
        print(f"✅ Statutory Invoice Number: {inv_data['invoice_number']}")
        print(f"✅ E-Invoice IRN Hash: {inv_data['irn_hash']}")
        print(f"✅ Requires E-Way Bill (> ₹50,000): {inv_data['requires_eway_bill']}")
        assert inv_data["irn_hash"] is not None, "B2B invoice should generate e-invoice IRN"
        assert inv_data["requires_eway_bill"] is True, "Consignment > ₹50,000 should require e-way bill"

        # TEST 3: Advance Deposit Credit Offset on Service Order
        print("\n--- Test 3: Advance Deposit Credit Offset ---")
        svc_payload = {
            "branch_id": branch_id,
            "channel": "service_order",
            "customer_name": "Rohan Deshmukh",
            "customer_phone": "9819998199",
            "customer_state_code": "27",
            "advance_offset_amount": 2500.0,  # Offset ₹2,500 advance paid during intake
            "lines": [
                {
                    "item_type": "service",
                    "name": "Level 4 Logic Board Micro-Soldering",
                    "hsn_sac_code": "9987",
                    "quantity": 1.0,
                    "unit_price": 5000.0,
                    "gst_rate": 18.0,
                }
            ],
            "payments": [
                {"method": "upi", "amount": 3400.0, "transaction_reference": "UPI/998822"},
            ],
        }
        res3 = await client.post("/api/v1/sales", json=svc_payload)
        assert res3.status_code == 201, f"Service sale failed: {res3.text}"
        sale3 = res3.json()
        print(f"✅ Service Order Sale: {sale3['sale_number']}")
        print(f"Grand Total: ₹{sale3['grand_total']:.2f}")
        print(f"Advance Offset: ₹{sale3['advance_offset_amount']:.2f}")
        print(f"Amount Paid Now: ₹{sale3['paid_amount']:.2f}")
        print(f"Balance Due: ₹{sale3['balance_due']:.2f}")
        assert sale3["advance_offset_amount"] == 2500.0, "Advance deposit must offset total"

        # TEST 4: Delivery Challan Dispatch
        print("\n--- Test 4: Delivery Challan Generation ---")
        dc_res = await client.post(
            "/api/v1/sales/challans",
            json={
                "sale_id": sale2["id"],
                "client_id": client_id,
                "challan_type": "delivery",
                "transporter_name": "BlueDart Express Logistics",
                "vehicle_number": "MH-02-CB-1234",
                "eway_bill_number": "EWB-202611-99881234",
                "items": [{"name": "MacBook Air M2 Retina Display", "quantity": 2.0}],
            },
        )
        assert dc_res.status_code == 201, f"Delivery challan failed: {dc_res.text}"
        dc_data = dc_res.json()
        print(f"✅ Delivery Challan Created: {dc_data['challan_number']} (Transporter: {dc_data['transporter_name']})")
        assert dc_data["status"] == "dispatched"

        # TEST 5: Credit Note Creation (Section 34 of CGST Act)
        print("\n--- Test 5: Statutory Credit Note ---")
        cn_res = await client.post(
            "/api/v1/sales/credit-notes",
            json={
                "invoice_id": inv_id,
                "reason": "Deficiency in Service",
                "taxable_amount": 5000.0,
                "igst_amount": 900.0,
                "notes": "Post-sale discount credited due to delayed component delivery",
            },
        )
        assert cn_res.status_code == 201, f"Credit note failed: {cn_res.text}"
        cn_data = cn_res.json()
        print(f"✅ Credit Note Number: {cn_data['credit_note_number']}")
        print(f"Credit Amount: ₹{cn_data['total_credit_amount']:.2f}")
        assert cn_data["total_credit_amount"] == 5900.0

        # TEST 6: Debit Note Creation
        print("\n--- Test 6: Statutory Debit Note ---")
        dn_res = await client.post(
            "/api/v1/sales/debit-notes",
            json={
                "invoice_id": inv_id,
                "reason": "Price Escalation",
                "taxable_amount": 1000.0,
                "igst_amount": 180.0,
                "notes": "Supplementary logistics surcharge",
            },
        )
        assert dn_res.status_code == 201, f"Debit note failed: {dn_res.text}"
        dn_data = dn_res.json()
        print(f"✅ Debit Note Number: {dn_data['debit_note_number']}")
        print(f"Debit Amount: ₹{dn_data['total_debit_amount']:.2f}")
        assert dn_data["total_debit_amount"] == 1180.0

        # TEST 7: Accounts Receivable (AR) Aging Table (30-day terms)
        print("\n--- Test 7: Accounts Receivable (AR) Aging Engine ---")
        ar_res = await client.get("/api/v1/sales/ar-aging")
        assert ar_res.status_code == 200, f"AR aging failed: {ar_res.text}"
        ar_data = ar_res.json()
        techcorp_ar = next((item for item in ar_data if item["client_name"] == "TechCorp India Pvt Ltd"), None)
        assert techcorp_ar is not None, "TechCorp should be present in AR aging"
        print(f"✅ Client: {techcorp_ar['client_name']}")
        print(f"Current 0-30 Days: ₹{techcorp_ar['current_0_30']:.2f}")
        print(f"Total Outstanding: ₹{techcorp_ar['total_outstanding']:.2f} (Limit: ₹{techcorp_ar['credit_limit']:.2f})")
        assert techcorp_ar["total_outstanding"] > 0

        # TEST 8: Bank Reconciliation for Payments
        print("\n--- Test 8: Bank Reconciliation (NEFT/RTGS UTR Match) ---")
        payments_list = (await client.get("/api/v1/sales")).json()[0]["payments"]
        if payments_list:
            pay_id = payments_list[0]["id"]
            recon_res = await client.post(
                f"/api/v1/sales/payments/{pay_id}/reconcile",
                json={
                    "bank_statement_reference": "STMT-HDFC-202611-BATCH01",
                    "notes": "Verified against HDFC Current Account Statement line 182",
                },
            )
            assert recon_res.status_code == 200, f"Recon failed: {recon_res.text}"
            recon_data = recon_res.json()
            print(f"✅ Payment {recon_data['payment_number']} Reconciled: {recon_data['is_reconciled']}")
            print(f"Bank Statement Ref: {recon_data['bank_statement_reference']}")
            assert recon_data["is_reconciled"] is True

        # TEST 9: Statutory GSTR-1 Report Generator
        print("\n--- Test 9: GSTR-1 Statutory Return Generator ---")
        gstr1_res = await client.get(f"/api/v1/sales/reports/gstr1?branch_id={branch_id}&month=11&year=2026")
        assert gstr1_res.status_code == 200, f"GSTR1 failed: {gstr1_res.text}"
        gstr1 = gstr1_res.json()
        print(f"✅ Month/Year: {gstr1['month_year']} | Branch GSTIN: {gstr1['branch_gstin']}")
        print(f"B2B Invoices Count: {len(gstr1['b2b_invoices'])}")
        print(f"HSN Summary Lines: {len(gstr1['hsn_summary'])}")
        print(f"Total Taxable Value: ₹{gstr1['total_taxable_value']:.2f}")
        print(f"CGST: ₹{gstr1['total_cgst']:.2f} | SGST: ₹{gstr1['total_sgst']:.2f} | IGST: ₹{gstr1['total_igst']:.2f}")
        assert len(gstr1["b2b_invoices"]) > 0, "B2B invoices should appear in Table 4 of GSTR-1"
        assert len(gstr1["hsn_summary"]) > 0, "HSN summary should appear in Table 12 of GSTR-1"

        # TEST 10: Statutory GSTR-3B Report Generator
        print("\n--- Test 10: GSTR-3B Monthly Return Summary ---")
        gstr3b_res = await client.get(f"/api/v1/sales/reports/gstr3b?branch_id={branch_id}&month=11&year=2026")
        assert gstr3b_res.status_code == 200, f"GSTR3B failed: {gstr3b_res.text}"
        gstr3b = gstr3b_res.json()
        print(f"✅ Table 3.1 Outward Taxable Supplies: ₹{gstr3b['table_3_1_outward_supplies']['taxable_value']:.2f}")
        print(f"Table 4 Eligible ITC: ₹{gstr3b['table_4_eligible_itc']['itc_all_other']:.2f}")
        print(f"Net Tax Payable (IGST): ₹{gstr3b['net_tax_payable']['integrated_tax']:.2f}")
        assert gstr3b["table_3_1_outward_supplies"]["taxable_value"] > 0

    print("\n==================================================")
    print("🏆 ALL 10 PHASE 5 BACKEND VERIFICATION SUITES PASSED!")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_phase5_tests())
