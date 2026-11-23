import asyncio
import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from httpx import AsyncClient, ASGITransport
from app.main import create_app
from app.db.session import AsyncSessionLocal
from app.models.branch import Branch
from sqlalchemy import select


async def main():
    print("🚀 Starting Phase 3 Backend Verification Test Suite...")
    app = create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Get active branch
        async with AsyncSessionLocal() as session:
            b_res = await session.execute(select(Branch).limit(1))
            branch = b_res.scalar_one_or_none()
            assert branch is not None, "A default branch must exist"
            branch_id = branch.id
            print(f"✅ Found branch: {branch.name} ({branch_id})")

        # 1. Test Service Catalog
        print("\n--- 1. Testing Service Catalog ---")
        srv_payload = {
            "branch_id": branch_id,
            "name": "Screen Replacement (AMOLED Display)",
            "category": "Screen & Display",
            "sac_code": "9987",
            "description": "Standard smartphone display assembly replacement with genuine adhesive seal",
            "labor_price": 1499.0,
            "duration_minutes": 45,
            "gst_rate": 18.0,
            "warranty_days": 180,
            "commission_rate": 15.0,
        }
        res = await client.post("/api/v1/services", json=srv_payload)
        assert res.status_code == 201, f"Failed: {res.text}"
        srv_data = res.json()
        print(f"✅ Created service rate card: {srv_data['name']} (SAC {srv_data['sac_code']}, ₹{srv_data['labor_price']})")
        service_id = srv_data["id"]

        res = await client.get("/api/v1/services?category=Screen%20%26%20Display")
        assert res.status_code == 200
        assert len(res.json()["items"]) >= 1
        print("✅ Verified service catalog listing and category filtering")

        # 2. Test Warehouse Location & Inventory Items
        print("\n--- 2. Testing Warehouse Locations & Inventory Items ---")
        loc_payload = {
            "branch_id": branch_id,
            "name": "Rack B - High Value Electronics",
            "code": "RACK-B-01",
            "is_default": True,
        }
        res = await client.post("/api/v1/inventory/locations", json=loc_payload)
        assert res.status_code == 201
        loc_data = res.json()
        location_id = loc_data["id"]
        print(f"✅ Created warehouse location: {loc_data['name']} ({loc_data['code']})")

        import random
        rand_num = random.randint(10000, 99999)
        sku = f"IP13-DISP-OEM-{rand_num}"
        barcode = f"890{rand_num}123456"

        item_payload = {
            "branch_id": branch_id,
            "name": "iPhone 13 OLED Assembly (OEM Grade)",
            "sku": sku,
            "barcode": barcode,
            "brand": "Apple",
            "model_compatibility": ["iPhone 13", "iPhone 13 mini"],
            "category": "Screens & Displays",
            "unit": "PCS",
            "hsn_code": "851770",
            "cost_price": 4500.0,
            "retail_price": 7999.0,
            "wholesale_price": 6500.0,
            "min_stock_level": 8.0,
            "max_stock_level": 50.0,
            "tax_rate": 18.0,
            "costing_method": "WAC",
            "track_inventory": True,
            "initial_stock": 5.0,  # Below min_stock_level (8.0) -> Should trigger low-stock alert!
            "warehouse_location_id": location_id,
        }
        res = await client.post("/api/v1/inventory", json=item_payload)
        assert res.status_code == 201, f"Failed: {res.text}"
        item_data = res.json()
        item_id = item_data["id"]
        print(f"✅ Created inventory item: {item_data['name']} (SKU: {item_data['sku']}, Stock: {item_data['current_stock']})")

        # Lookup by barcode scanner
        res = await client.get(f"/api/v1/inventory/lookup?code={barcode}")
        assert res.status_code == 200
        assert res.json()["id"] == item_id
        print("✅ Barcode / SKU scanner lookup succeeded")

        # Low stock alert check
        res = await client.get("/api/v1/inventory/low-stock")
        assert res.status_code == 200
        low_items = res.json()
        matching = [i for i in low_items if i["item_id"] == item_id]
        assert len(matching) == 1, "Item with 5 qty (min 8) must appear in low-stock alerts"
        print(f"✅ Low-stock reorder query triggered: Shortfall = {matching[0]['shortfall']} units, Reorder cost = ₹{matching[0]['estimated_reorder_cost']}")

        # 3. Test Suppliers
        print("\n--- 3. Testing Suppliers & Commercial Terms ---")
        supp_payload = {
            "branch_id": branch_id,
            "name": "Apex Electronics & Spares Pvt Ltd",
            "supplier_type": "legal_entity",
            "contact_name": "Vikram Sethi",
            "phone": "9820011223",
            "email": "procurement@apexspares.in",
            "gstin": "27AABCA1234F1Z6",
            "credit_period_days": 45,
            "credit_limit": 500000.0,
            "payment_terms": "Net 45 Days",
            "city": "Mumbai",
            "state": "Maharashtra",
            "state_code": "27",
            "bank_details": {
                "account_number": "001234567890",
                "ifsc": "HDFC0001234",
                "bank_name": "HDFC Bank",
            },
            "tags": ["OEM", "Wholesale", "Screens"],
        }
        res = await client.post("/api/v1/suppliers", json=supp_payload)
        assert res.status_code == 201, f"Failed: {res.text}"
        supp_data = res.json()
        supplier_id = supp_data["id"]
        print(f"✅ Created supplier: {supp_data['name']} (GSTIN: {supp_data['gstin']}, Terms: {supp_data['payment_terms']})")

        # 4. Test Purchase Order & Approval
        print("\n--- 4. Testing Purchase Order Workflow ---")
        po_payload = {
            "branch_id": branch_id,
            "supplier_id": supplier_id,
            "notes": "Urgent stock replenishment for screen inventory",
            "items": [
                {
                    "inventory_item_id": item_id,
                    "quantity_ordered": 10.0,
                    "unit_cost": 4500.0,
                    "tax_rate": 18.0,
                }
            ],
        }
        res = await client.post("/api/v1/procurement/purchase-orders", json=po_payload)
        assert res.status_code == 201, f"Failed: {res.text}"
        po_data = res.json()
        po_id = po_data["id"]
        po_item_id = po_data["items"][0]["id"]
        print(f"✅ Created Purchase Order {po_data['po_number']}: Subtotal = ₹{po_data['subtotal']}, Grand Total = ₹{po_data['grand_total']}")

        # Manager Approval
        res = await client.put(f"/api/v1/procurement/purchase-orders/{po_id}/approve")
        assert res.status_code == 200
        assert res.json()["status"] == "Approved"
        print(f"✅ Approved Purchase Order {po_data['po_number']}")

        # 5. Test Goods Received Note (GRN) & 3-Way Match
        print("\n--- 5. Testing Goods Received Note (GRN) & 3-Way Match ---")
        grn_payload = {
            "branch_id": branch_id,
            "purchase_order_id": po_id,
            "supplier_id": supplier_id,
            "vendor_invoice_no": "INV-APEX-8891",
            "vendor_invoice_amount": 53100.0,  # 10 * 4500 * 1.18 = 53100 (Exact match)
            "notes": "Inbound intake: 10 units received, 9 accepted, 1 transit damage",
            "items": [
                {
                    "inventory_item_id": item_id,
                    "po_item_id": po_item_id,
                    "warehouse_location_id": location_id,
                    "quantity_received": 10.0,
                    "quantity_accepted": 9.0,
                    "quantity_damaged": 1.0,
                    "batch_number": "BAT-2026-X1",
                    "unit_cost": 4500.0,
                    "notes": "1 unit has hairline crack on bezel",
                }
            ],
        }
        res = await client.post("/api/v1/procurement/grns", json=grn_payload)
        assert res.status_code == 201, f"Failed: {res.text}"
        grn_data = res.json()
        grn_id = grn_data["id"]
        print(f"✅ Inbound GRN {grn_data['grn_number']} processed: 9 accepted into stock, 1 damaged")

        # Verify stock increased by 9
        res = await client.get(f"/api/v1/inventory/{item_id}")
        assert res.status_code == 200
        new_stock = res.json()["current_stock"]
        assert new_stock == 14.0, f"Expected 5 + 9 = 14 stock, got {new_stock}"
        print(f"✅ Stock Ledger updated automatically: Current Stock on Hand = {new_stock} units")

        # Check 3-Way Match
        res = await client.get(f"/api/v1/procurement/grns/{grn_id}/three-way-match")
        assert res.status_code == 200
        match_data = res.json()
        print(f"✅ 3-Way Match Evaluation: PO #{match_data['po_number']} vs GRN #{match_data['grn_number']} vs Invoice #{match_data['vendor_invoice_no']}")
        print(f"   Match status: {match_data['overall_match_status']}, Quantity variance: {match_data['match_lines'][0]['quantity_variance']}")

        # 6. Test Scrap / Damage Write-Off
        print("\n--- 6. Testing Scrap / Damage Write-Off ---")
        scrap_payload = {
            "branch_id": branch_id,
            "inventory_item_id": item_id,
            "warehouse_location_id": location_id,
            "quantity": 1.0,
            "reason_code": "damaged_in_transit",
            "notes": "Damaged unit from GRN delivery written off with vendor return credit pending",
        }
        res = await client.post("/api/v1/procurement/scrap", json=scrap_payload)
        assert res.status_code == 201, f"Failed: {res.text}"
        scrap_data = res.json()
        print(f"✅ Created scrap write-off voucher {scrap_data['voucher_number']}: Total Loss = ₹{scrap_data['total_cost']}")

        # Stock should now be 14 - 1 = 13
        res = await client.get(f"/api/v1/inventory/{item_id}")
        assert res.json()["current_stock"] == 13.0
        print("✅ Stock ledger adjusted for scrap write-off: Balance = 13.0")

        # 7. Test Stocktaking Session & Adjustment Voucher
        print("\n--- 7. Testing Stocktaking Session & Adjustment ---")
        stk_payload = {
            "branch_id": branch_id,
            "audit_type": "blind_count",
            "notes": "Monthly physical audit for displays",
        }
        res = await client.post("/api/v1/procurement/stocktaking", json=stk_payload)
        assert res.status_code == 201, f"Failed: {res.text}"
        audit_data = res.json()
        audit_id = audit_data["id"]
        print(f"✅ Started Stocktake session {audit_data['audit_number']} ({audit_data['audit_type']})")

        # Scan counted quantity: suppose physical count is 14 (found 1 extra unit)
        scan_payload = {
            "inventory_item_id": item_id,
            "warehouse_location_id": location_id,
            "counted_quantity": 14.0,  # Expected was 13 -> variance = +1.0
            "manager_notes": "Found extra unopened piece on Shelf 3",
        }
        res = await client.post(f"/api/v1/procurement/stocktaking/{audit_id}/scan", json=scan_payload)
        assert res.status_code == 200
        scan_result = res.json()
        assert scan_result["variance"] == 1.0
        print(f"✅ Logged physical scan: Counted = {scan_result['counted_quantity']}, Expected = {scan_result['expected_quantity']}, Variance = {scan_result['variance']}")

        # Generate Adjustment Voucher
        res = await client.post(f"/api/v1/procurement/stocktaking/{audit_id}/adjust")
        assert res.status_code == 200
        adj_result = res.json()
        print(f"✅ Adjustment Voucher Applied: {adj_result['message']}")

        # Stock should now be reconciled to exactly 14.0
        res = await client.get(f"/api/v1/inventory/{item_id}")
        assert res.json()["current_stock"] == 14.0
        print(f"✅ Stock ledger successfully reconciled: Final verified stock = {res.json()['current_stock']}")

    print("\n🎉 ALL PHASE 3 BACKEND TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(main())
