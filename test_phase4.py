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
from app.models.asset import Asset
from app.models.inventory import InventoryItem, WarehouseLocation, StockLedger, StockReservation
from app.models.service_catalog import ServiceCatalogItem
from app.models.supplier import Supplier
from app.services.inventory_service import InventoryService
from sqlalchemy import select


async def run_phase4_tests():
    print("==================================================")
    print("🚀 STARTING PHASE 4 CORE MODULE VERIFICATION SUITE")
    print("==================================================")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Step 0: Ensure base test data exists in db
        async with AsyncSessionLocal() as db:
            # Check or create branch
            branch_res = await db.execute(select(Branch).limit(1))
            branch = branch_res.scalar_one_or_none()
            if not branch:
                branch = Branch(name="Test Mumbai Hub", code="BR-TEST-01", state_code="27", currency="INR")
                db.add(branch)
                await db.flush()

            # Create test client
            test_client = Client(
                name="Sanjay Sharma",
                phone="9820098200",
                email="sanjay.sharma@example.com",
                client_type="individual",
                branch_id=branch.id,
            )
            db.add(test_client)
            await db.flush()

            # Create test asset
            test_asset = Asset(
                client_id=test_client.id,
                branch_id=branch.id,
                name="iPhone 14 Pro Max",
                brand="Apple",
                model="A2894",
                asset_type="mobile",
                identifier="IMEI-358921098234123",
                warranty_status="expired",
            )
            db.add(test_asset)
            await db.flush()

            # Create test supplier
            supplier = Supplier(
                branch_id=branch.id,
                name="Shenzhen Foxconn Spares Ltd",
                contact_name="Kevin Li",
                phone="9988776655",
                supplier_type="legal_entity",
            )
            db.add(supplier)
            await db.flush()

            import secrets
            rand_suffix = secrets.token_hex(3)
            # Create test inventory items: Item 1 with stock, Item 2 without stock
            item_in_stock = InventoryItem(
                branch_id=branch.id,
                name=f"iPhone 14 Pro OLED Display Assembly {rand_suffix}",
                sku=f"SP-IP14P-DISP-{rand_suffix}",
                barcode=f"BC-{rand_suffix}-01",
                cost_price=7500.0,
                retail_price=12500.0,
                min_stock_level=2.0,
                tax_rate=18.0,
            )
            db.add(item_in_stock)
            await db.flush()

            # Add initial stock of 5 pcs via inventory service
            await InventoryService.record_stock_movement(
                session=db,
                branch_id=branch.id,
                inventory_item_id=item_in_stock.id,
                movement_type="PURCHASE_GRN",
                quantity_change=5.0,
                unit_cost=7500.0,
                reference_type="INIT",
            )

            item_out_of_stock = InventoryItem(
                branch_id=branch.id,
                name=f"iPhone 14 Pro Logic Board 256GB {rand_suffix}",
                sku=f"SP-IP14P-MB-{rand_suffix}",
                barcode=f"BC-{rand_suffix}-02",
                cost_price=15000.0,
                retail_price=22000.0,
                min_stock_level=1.0,
                tax_rate=18.0,
            )
            db.add(item_out_of_stock)
            await db.flush()

            # Service catalog item
            labor_item = ServiceCatalogItem(
                branch_id=branch.id,
                name="Display Replacement Labor & Waterproofing",
                sac_code="9987",
                category="Mobile Repair",
                labor_price=1500.0,
                gst_rate=18.0,
                duration_minutes=45,
            )
            db.add(labor_item)
            await db.commit()

            branch_id = branch.id
            client_id = test_client.id
            asset_id = test_asset.id
            item_stock_id = item_in_stock.id
            item_nostock_id = item_out_of_stock.id
            service_id = labor_item.id

        # TEST 1: Ticket Intake Creation
        print("\n--- Test 1: Ticket Intake Creation ---")
        intake_payload = {
            "branch_id": branch_id,
            "client_id": client_id,
            "asset_id": asset_id,
            "ticket_type": "service",
            "priority": "high",
            "intake_source": "counter",
            "problem_reported": "Cracked OLED screen and lines on display after drop.",
            "customer_max_repair_budget": 10000.0,  # Ceiling ₹10,000
            "advance_deposit": 2000.0,
            "dynamic_fields": {"screen_lock_pin": "1234", "backup_confirmed": True},
        }
        res = await client.post("/api/v1/tickets", json=intake_payload)
        assert res.status_code == 201, f"Failed ticket intake: {res.text}"
        ticket_data = res.json()
        ticket_id = ticket_data["id"]
        tracking_token = ticket_data["tracking_token"]
        ticket_number = ticket_data["ticket_number"]
        print(f"✅ Ticket created: {ticket_number} (ID: {ticket_id})")
        print(f"✅ Advance Deposit: ₹{ticket_data['advance_deposit']:.2f}")
        print(f"✅ 128-bit Tracking Token: {tracking_token}")
        assert len(tracking_token) == 32, "Tracking token should be 32 hex chars (128 bits)"

        # TEST 2: Public Tracking Endpoint (Non-Authenticated)
        print("\n--- Test 2: Public Customer Tracking Lookup ---")
        track_res = await client.get(f"/api/v1/tickets/track/{tracking_token}")
        assert track_res.status_code == 200, f"Tracking failed: {track_res.text}"
        track_data = track_res.json()
        print(f"✅ Public tracking verified for Device: {track_data['asset_name']} ({track_data['status']})")
        assert track_data["ticket_number"] == ticket_number

        # TEST 3: Add Part with In-Stock Quantity -> Auto-Reserve
        print("\n--- Test 3: Add Part with Stock Reservation ---")
        part_res = await client.post(
            f"/api/v1/tickets/{ticket_id}/parts",
            json={"inventory_item_id": item_stock_id, "quantity": 1.0, "unit_price": 12500.0},
        )
        assert part_res.status_code == 200, f"Add part failed: {part_res.text}"
        part_data = part_res.json()
        assert part_data["is_reserved"] is True, "In-stock part should be reserved"
        print(f"✅ Part added & reserved: {part_data['item_name']} (Total: ₹{part_data['total_price']:.2f})")

        # TEST 4: Threshold Pause Gate Verification
        print("\n--- Test 4: Threshold Pause Gate Check ---")
        ticket_chk = await client.get(f"/api/v1/tickets/{ticket_id}")
        t_data = ticket_chk.json()
        print(f"Grand Total: ₹{t_data['grand_total']:.2f} vs Budget: ₹{t_data['customer_max_repair_budget']:.2f}")
        print(f"Is Paused: {t_data['is_paused']} (Reason: {t_data['pause_reason']})")
        assert t_data["is_paused"] is True, "Ticket should be paused because grand total exceeds customer max repair budget"

        # TEST 5: Add Part with Stock Shortage -> "spare_wait" + Auto PO Draft
        print("\n--- Test 5: Stock Shortage Gate & Auto PO Draft ---")
        shortage_res = await client.post(
            f"/api/v1/tickets/{ticket_id}/parts",
            json={"inventory_item_id": item_nostock_id, "quantity": 1.0},
        )
        assert shortage_res.status_code == 200, f"Add shortage part failed: {shortage_res.text}"
        ticket_after_shortage = (await client.get(f"/api/v1/tickets/{ticket_id}")).json()
        print(f"✅ Ticket Status after shortage: {ticket_after_shortage['status']}")
        print(f"✅ Pause Reason: {ticket_after_shortage['pause_reason']}")
        assert ticket_after_shortage["status"] == "spare_wait", "Shortage should trigger spare_wait status"

        # Check that draft PO was automatically created in procurement
        po_res = await client.get("/api/v1/procurement/purchase-orders")
        assert po_res.status_code == 200
        po_data = po_res.json()
        po_list = po_data.get("items", po_data) if isinstance(po_data, dict) else po_data
        assert any(ticket_number in (po.get("notes") or "") for po in po_list), "Auto draft PO should be created"
        print("✅ Auto-drafted Purchase Order confirmed in procurement system")

        # TEST 6: Labor Operation & Technician Commission
        print("\n--- Test 6: Labor Operation & Technician Commission ---")
        labor_res = await client.post(
            f"/api/v1/tickets/{ticket_id}/labor",
            json={
                "service_catalog_item_id": service_id,
                "name": "Screen Replacement Labor",
                "labor_price": 1500.0,
                "commission_rate": 20.0,  # 20% commission = ₹300
                "duration_minutes": 45,
            },
        )
        assert labor_res.status_code == 200, f"Add labor failed: {labor_res.text}"
        labor_data = labor_res.json()
        print(f"✅ Labor added: {labor_data['name']} (Price: ₹{labor_data['labor_price']:.2f})")
        print(f"✅ Technician Commission: ₹{labor_data['commission_amount']:.2f} ({labor_data['commission_rate']}%)")
        assert labor_data["commission_amount"] == 300.0, "Commission should be 20% of ₹1500 = ₹300"

        # TEST 7: Estimate Generation & 1-Click Tokenized Customer Approval
        print("\n--- Test 7: Estimate Generation & 1-Click Approval Link ---")
        est_res = await client.post(
            f"/api/v1/tickets/{ticket_id}/estimates",
            json={"customer_notes": "Please review quote for OLED display + motherboard + labor."},
        )
        assert est_res.status_code == 200, f"Estimate failed: {est_res.text}"
        est_data = est_res.json()
        est_token = est_data["approval_token"]
        print(f"✅ Estimate created: {est_data['estimate_number']} (Grand Total: ₹{est_data['grand_total']:.2f})")
        print(f"✅ 1-Click Approval Token: {est_token}")

        # Customer approves estimate via token
        approve_res = await client.post(
            f"/api/v1/tickets/estimates/{est_token}/approve",
            json={"action": "approve"},
        )
        assert approve_res.status_code == 200, f"Estimate approval failed: {approve_res.text}"
        approved_est = approve_res.json()
        print(f"✅ Estimate Status: {approved_est['approval_status']} at {approved_est['approved_at']}")
        assert approved_est["approval_status"] == "approved"

        # TEST 8: Subcontract External Machining Task
        print("\n--- Test 8: Subcontract External Repair Task ---")
        sub_res = await client.post(
            f"/api/v1/tickets/{ticket_id}/subcontract",
            json={
                "vendor_name": "Apex Micro-Soldering Lab",
                "vendor_phone": "9819998199",
                "task_description": "Level 4 BGA micro-soldering on power IC",
                "cost": 2200.0,
                "charged_to_customer": 3500.0,
            },
        )
        assert sub_res.status_code == 200, f"Subcontract failed: {sub_res.text}"
        sub_data = sub_res.json()
        print(f"✅ Subcontract task created: {sub_data['vendor_name']} (Status: {sub_data['status']})")

        # Update subcontract to returned
        sub_update = await client.put(
            f"/api/v1/tickets/subcontract/{sub_data['id']}",
            json={"status": "returned"},
        )
        assert sub_update.status_code == 200
        print("✅ Subcontract task returned from vendor")

        # TEST 9: Quality Assurance (QA) Checklist
        print("\n--- Test 9: QA Checklist Verification ---")
        qa_res = await client.put(
            f"/api/v1/tickets/{ticket_id}/qa-checklist",
            json={
                "qa_status": "passed",
                "qa_checklist": [
                    {"id": "1", "label": "Multi-touch 10-point test", "checked": True, "notes": "Passed"},
                    {"id": "2", "label": "Proximity sensor check", "checked": True, "notes": "Passed"},
                    {"id": "3", "label": "Ear speaker and microphone test", "checked": True, "notes": "Passed"},
                    {"id": "4", "label": "Clean chassis and screen protector", "checked": True, "notes": "Passed"},
                ],
            },
        )
        assert qa_res.status_code == 200, f"QA update failed: {qa_res.text}"
        qa_data = qa_res.json()
        print(f"✅ QA Checklist Status: {qa_data['qa_status']} with {len(qa_data['qa_checklist'])} passed checks")
        assert qa_data["qa_status"] == "passed"

        # TEST 10: Handover & Delivery Closure Gate
        print("\n--- Test 10: Closure Gate & Delivery Handover Settlement ---")
        ticket_before_delivery = (await client.get(f"/api/v1/tickets/{ticket_id}")).json()
        bal = ticket_before_delivery["balance_due"]
        print(f"Outstanding Balance Due: ₹{bal:.2f}")

        # Try to deliver without settling balance and without manager override -> Expect 400
        fail_delivery = await client.post(
            f"/api/v1/tickets/{ticket_id}/handover",
            json={
                "handover_recipient": "Sanjay Sharma",
                "payment_amount": 0.0,
                "manager_override": False,
            },
        )
        assert fail_delivery.status_code == 400, "Should block delivery when balance > 0 and no manager override"
        print(f"✅ Closure gate successfully blocked delivery: {fail_delivery.json()['detail']}")

        # Now settle remaining balance in full
        delivery_res = await client.post(
            f"/api/v1/tickets/{ticket_id}/handover",
            json={
                "handover_recipient": "Sanjay Sharma",
                "payment_method": "upi",
                "payment_amount": bal,
                "handover_signature": "data:image/svg+xml;base64,PHN2Zy...",
                "manager_override": False,
                "notes": "Delivered with 90-day warranty card.",
            },
        )
        assert delivery_res.status_code == 200, f"Delivery failed: {delivery_res.text}"
        delivered_ticket = delivery_res.json()
        print(f"✅ Ticket delivered! Status: {delivered_ticket['status']}")
        print(f"✅ Balance Due: ₹{delivered_ticket['balance_due']:.2f}")
        print(f"✅ Handover Recipient: {delivered_ticket['handover_recipient']} at {delivered_ticket['handover_at']}")
        assert delivered_ticket["status"] == "delivered"
        assert delivered_ticket["balance_due"] == 0.0

        # TEST 11: Printable Intake Slip Data
        print("\n--- Test 11: Printable Intake Slip Generation ---")
        slip_res = await client.get(f"/api/v1/tickets/{ticket_id}/intake-slip")
        assert slip_res.status_code == 200, f"Slip failed: {slip_res.text}"
        slip_data = slip_res.json()
        print(f"✅ Intake Slip Type: {slip_data['slip_type']}")
        print(f"✅ Barcode Code128: {slip_data['barcode_code128']}")
        print(f"✅ Tracking URL: {slip_data['tracking_url']}")
        print(f"✅ Terms items: {len(slip_data['terms_and_conditions'])}")
        assert slip_data["barcode_code128"] == ticket_number

    print("\n==================================================")
    print("🏆 ALL 11 PHASE 4 BACKEND VERIFICATION SUITES PASSED!")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_phase4_tests())
