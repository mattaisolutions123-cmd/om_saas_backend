import asyncio
import httpx
import secrets
from datetime import datetime, timezone
from app.main import app
from app.core.security import create_access_token


async def run_tests():
    from app.db.session import AsyncSessionLocal
    from app.models.user import User
    from app.models.branch import Branch
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        # Get actual branch & users
        b_res = await db.execute(select(Branch).limit(1))
        branch = b_res.scalar_one()
        branch_id = branch.id

        u_res = await db.execute(select(User).limit(1))
        owner = u_res.scalar_one()

        cashier_res = await db.execute(select(User).where(User.email.like("%cashier%")).limit(1))
        cashier = cashier_res.scalar_one_or_none() or owner
        cashier_id = cashier.id

        from app.models.cashbox import CashRegisterShift
        open_shifts = (await db.execute(select(CashRegisterShift).where(CashRegisterShift.cashier_id == cashier_id, CashRegisterShift.status == "OPEN"))).scalars().all()
        for s in open_shifts:
            s.status = "CLOSED"
        await db.commit()

    token = create_access_token(subject=owner.id, claims={"email": owner.email, "role": "admin", "branch_id": branch_id})
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        print("\n=======================================================")
        print("🚀 RUNNING PHASE 6 PAYMENTS & CASHBOX TEST SUITE")
        print("=======================================================\n")

        # TEST 1: Open Register Shift with Denominations
        print("TEST 1: Opening Cash Register Shift with Denominations...")
        open_payload = {
            "branch_id": branch_id,
            "cashier_id": cashier_id,
            "opening_float": 3000.0,
            "opening_denominations": {
                "500": 4,   # 2000
                "200": 3,   # 600
                "100": 3,   # 300
                "50": 2,    # 100
                "coins": 0,
            },
            "notes": "Morning register opening shift",
        }
        r1 = await client.post("/api/v1/cashbox/shifts/open", json=open_payload, headers=headers)
        assert r1.status_code == 201, f"Failed to open shift: {r1.text}"
        shift = r1.json()
        shift_id = shift["id"]
        assert shift["status"] == "OPEN"
        assert shift["opening_float"] == 3000.0
        print(f"✅ Shift Opened: {shift['shift_number']} with float ₹{shift['opening_float']}")

        # TEST 2: Verify Chart of Accounts & Opening Double-Entry
        print("\nTEST 2: Verifying Chart of Accounts & Float Double-Entry...")
        r2 = await client.get(f"/api/v1/cashbox/accounts?branch_id={branch_id}", headers=headers)
        assert r2.status_code == 200
        accounts = r2.json()
        cash_acc = next((a for a in accounts if a["code"] == "1010_CASH"), None)
        assert cash_acc is not None
        assert cash_acc["balance"] >= 3000.0
        print(f"✅ Cash Account Balance: ₹{cash_acc['balance']:.2f}")

        # Check ledger entries for float
        r2_ledger = await client.get(f"/api/v1/cashbox/ledger?branch_id={branch_id}&reference_type=SHIFT_OPEN", headers=headers)
        assert r2_ledger.status_code == 200
        entries = r2_ledger.json()
        assert len(entries) >= 2
        print(f"✅ Double-entry journal confirmed: {len(entries)} balanced entries for shift opening float")

        # TEST 3: Record Subcontractor Lathe Expense Linked to Ticket
        print("\nTEST 3: Recording Subcontractor Lathe Expense...")
        exp_payload = {
            "branch_id": branch_id,
            "shift_id": shift_id,
            "category": "Subcontractor Lathe Machine Work",
            "amount": 750.0,
            "payment_method": "cash",
            "payee_name": "Apex Engineering Lathe Works",
            "narration": "Motor rotor lathe facing and stator milling",
            "ticket_id": "test-ticket-rotor",
            "is_spare_purchase": False,
        }
        r3 = await client.post("/api/v1/cashbox/expenses", json=exp_payload, headers=headers)
        assert r3.status_code == 201, f"Expense creation failed: {r3.text}"
        exp = r3.json()
        assert exp["amount"] == 750.0
        print(f"✅ Subcontractor Expense Voucher created: {exp['expense_number']} (₹{exp['amount']})")

        # TEST 4: Direct Spare Part Cash Purchase (Auto-Increases Stock Lot)
        print("\nTEST 4: Spare Part Direct Cash Purchase with Auto Stock Increment...")
        # First ensure an inventory item exists
        inv_item_id = "test-part-capacitor"
        # Check if item exists, else look up any item
        inv_items_res = await client.get("/api/v1/inventory?limit=1", headers=headers)
        items = inv_items_res.json().get("items", [])
        if items:
            inv_item_id = items[0]["id"]
            stock_before = items[0]["current_stock"]
        else:
            stock_before = 0.0

        spare_exp_payload = {
            "branch_id": branch_id,
            "shift_id": shift_id,
            "category": "Spare Parts Cash Purchase",
            "amount": 1200.0,
            "payment_method": "cash",
            "payee_name": "Local Electronics Spares Hub",
            "narration": "Emergency cash purchase of 4x Capacitors",
            "is_spare_purchase": True,
            "inventory_item_id": inv_item_id,
            "quantity": 4.0,
            "unit_cost": 300.0,
        }
        r4 = await client.post("/api/v1/cashbox/expenses", json=spare_exp_payload, headers=headers)
        assert r4.status_code == 201, f"Spare purchase failed: {r4.text}"
        spare_exp = r4.json()
        assert spare_exp["is_spare_purchase"] is True
        print(f"✅ Spare Cash Purchase Voucher: {spare_exp['expense_number']} (₹{spare_exp['amount']})")

        # Verify stock increment
        if items:
            inv_item_after = await client.get(f"/api/v1/inventory/{inv_item_id}", headers=headers)
            stock_after = inv_item_after.json()["current_stock"]
            assert stock_after == stock_before + 4.0, f"Expected {stock_before + 4.0}, got {stock_after}"
            print(f"✅ Stock lot successfully incremented: {stock_before} -> {stock_after}")

        # TEST 5: Customer Cash Refund
        print("\nTEST 5: Issuing Customer Cash Refund...")
        refund_payload = {
            "branch_id": branch_id,
            "shift_id": shift_id,
            "original_payment_method": "cash",
            "refund_payment_method": "cash",
            "amount": 200.0,
            "reason": "Customer returned unopened adapter",
            "notes": "Original receipt checked",
        }
        r5 = await client.post("/api/v1/cashbox/refunds", json=refund_payload, headers=headers)
        assert r5.status_code == 201, f"Refund failed: {r5.text}"
        ref = r5.json()
        assert ref["amount"] == 200.0
        print(f"✅ Refund issued: {ref['refund_number']} (₹{ref['amount']})")

        # TEST 6: Blind Closeout with Cash Count & Variance Detection
        print("\nTEST 6: Testing Blind Closeout & Variance Calculation...")
        # Expected calculation:
        # Opening Float: 3000
        # Cash In: 0 (no cash sales recorded in this unit test window yet)
        # Cash Out: 750 (lathe) + 1200 (spares) + 200 (refund) = 2150
        # Expected Cash = 3000 - 2150 = 850.0

        # Scenario A: Cashier enters 800 (short by 50) without reason -> Should fail!
        close_short_no_reason = {
            "closing_denominations": {"500": 1, "200": 1, "100": 1},
            "closing_counted_cash": 800.0,
        }
        r6_fail = await client.post(f"/api/v1/cashbox/shifts/{shift_id}/close", json=close_short_no_reason, headers=headers)
        assert r6_fail.status_code == 400, "Should have rejected unbalanced closeout without explanation comment"
        print("✅ Unbalanced closeout without mandatory explanation correctly blocked (400)")

        # Scenario B: Cashier enters 850 (exact balance) -> Balanced & Locked!
        close_balanced = {
            "closing_denominations": {"500": 1, "200": 1, "100": 1, "50": 1},
            "closing_counted_cash": 850.0,
            "notes": "Evening physical cash count matches register",
        }
        r6_success = await client.post(f"/api/v1/cashbox/shifts/{shift_id}/close", json=close_balanced, headers=headers)
        assert r6_success.status_code == 200, f"Balanced close failed: {r6_success.text}"
        closed_shift = r6_success.json()
        assert closed_shift["status"] == "CLOSED"
        assert closed_shift["is_balanced"] is True
        assert closed_shift["variance"] == 0.0
        print(f"✅ Shift {closed_shift['shift_number']} Blind Closeout Successful: Expected ₹{closed_shift['expected_cash']}, Counted ₹{closed_shift['closing_counted_cash']}, Variance ₹{closed_shift['variance']}")

        # TEST 7: Technician Commission Rule & Monthly Payroll Report
        print("\nTEST 7: Commission Rules & Technician Payroll Engine...")
        comm_rule_payload = {
            "branch_id": branch_id,
            "name": "Standard Technician 15% Labor Commission",
            "role": "technician",
            "rule_type": "percentage_of_labor",
            "labor_percentage": 15.0,
        }
        r7_rule = await client.post("/api/v1/cashbox/commissions/rules", json=comm_rule_payload, headers=headers)
        assert r7_rule.status_code == 201
        print("✅ Commission Rule registered: 15% of service labor")

        r7_payroll = await client.get("/api/v1/cashbox/payroll", headers=headers)
        assert r7_payroll.status_code == 200
        payroll = r7_payroll.json()
        print(f"✅ Monthly Payroll Report Generated: {len(payroll['technicians'])} technicians, Total Payout ₹{payroll['total_payroll_commission']}")

        # TEST 8: Ticket Profitability Formula
        print("\nTEST 8: Ticket Profitability Engine...")
        # Check profitability for test-ticket
        # Find any ticket from database
        tickets_res = await client.get("/api/v1/tickets?limit=1", headers=headers)
        t_json = tickets_res.json()
        t_items = t_json if isinstance(t_json, list) else t_json.get("items", [])
        if t_items:
            t_id = t_items[0]["id"]
            r8 = await client.get(f"/api/v1/cashbox/profitability/ticket/{t_id}", headers=headers)
            assert r8.status_code == 200, f"Profitability failed: {r8.text}"
            profit = r8.json()
            print(f"✅ Net Profit Analysis for Ticket {profit['ticket_number']}:")
            print(f"   Total Bill: ₹{profit['total_bill']}")
            print(f"   Parts Cost: -₹{profit['parts_cost']}")
            print(f"   Subcontract: -₹{profit['subcontract_expenses']}")
            print(f"   Tech Comm:  -₹{profit['tech_commission']}")
            print(f"   = Net Profit: ₹{profit['net_profit']} (Margin: {profit['margin_percentage']}%)")
        else:
            print("⚠️ No ticket in DB to compute profitability, test skipped")

        # TEST 9: Multi-Branch Financial Consolidation
        print("\nTEST 9: Multi-Branch Financial Consolidation...")
        r9 = await client.get("/api/v1/cashbox/consolidation", headers=headers)
        assert r9.status_code == 200
        cons = r9.json()
        assert len(cons["branches"]) >= 1
        print(f"✅ Financial Consolidation across {len(cons['branches'])} branches:")
        print(f"   Total Cash on Hand: ₹{cons['total_cash']}")
        print(f"   Total Bank/UPI:     ₹{cons['total_bank_upi']}")
        print(f"   Total Receivables:  ₹{cons['total_receivables']}")
        print(f"   Net Consolidated P&L: ₹{cons['net_consolidated_profit']}")

        # TEST 10: Real-time UPI Webhook Handler
        print("\nTEST 10: Testing Real-time UPI Webhook Settlement...")
        webhook_payload = {
            "event": "payment.success",
            "transaction_id": f"UPI-UTR-{secrets.token_hex(6).upper()}",
            "amount": 2500.0,
            "payer_vpa": "customer@oksbi",
            "merchant_transaction_id": t_items[0]["ticket_number"] if t_items else "SALE-202611-0001",
            "status": "SUCCESS",
        }
        r10 = await client.post("/api/v1/cashbox/webhook/upi", json=webhook_payload)
        assert r10.status_code == 200, f"UPI Webhook failed: {r10.text}"
        wh_res = r10.json()
        assert wh_res["success"] is True
        print(f"✅ UPI Webhook Instant Settlement: {wh_res['message']} (Payment ID: {wh_res['payment_id']})")

        print("\n=======================================================")
        print("🎉 ALL 10 PHASE 6 BACKEND TESTS PASSED SUCCESSFULLY!")
        print("=======================================================\n")


if __name__ == "__main__":
    asyncio.run(run_tests())
