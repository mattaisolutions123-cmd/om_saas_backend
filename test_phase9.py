import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
import secrets

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.session import AsyncSessionLocal
from app.models.branch import Branch
from app.models.user import User
from app.models.client import Client
from app.models.asset import Asset
from app.models.ticket import Ticket, TicketPart, TicketLabor, TicketEstimate
from app.models.inventory import InventoryItem, StockLedger
from app.models.payment_transaction import PaymentTransaction
from app.models.scheduled_report import ScheduledReport
from app.services.analytics_service import AnalyticsService
from app.services.reports_service import ReportsService
from app.core.security import create_access_token
from app.models.base import utc_now, to_utc
from sqlalchemy import select


async def run_phase9_tests():
    print("==================================================")
    print("🚀 STARTING PHASE 9 ADVANCED ANALYTICS & 18+ REPORTS SUITE")
    print("==================================================")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Step 0: Ensure base test data
        async with AsyncSessionLocal() as db:
            # 1. Branch
            b_res = await db.execute(select(Branch).limit(1))
            branch = b_res.scalar_one_or_none()
            if not branch:
                branch = Branch(name="OmniSuite Analytics Hub", code="BR-HQ-P9", state_code="27", currency="INR")
                db.add(branch)
                await db.flush()
            branch_id = branch.id

            # 2. Users (Owner, Manager, Tech)
            u_res = await db.execute(select(User).limit(5))
            users = u_res.scalars().all()
            owner_user = None
            manager_user = None
            tech_user = None

            for u in users:
                role_slug = u.role.slug if u.role else ""
                if "owner" in role_slug or "admin" in role_slug:
                    owner_user = u
                elif "manager" in role_slug:
                    manager_user = u
                elif "technician" in role_slug:
                    tech_user = u

            if not owner_user:
                owner_user = users[0]
            if not manager_user:
                manager_user = users[0]
            if not tech_user:
                tech_user = users[min(1, len(users) - 1)]

            # 3. Inventory item for stock valuation
            inv_res = await db.execute(select(InventoryItem).limit(1))
            inv_item = inv_res.scalar_one_or_none()
            if not inv_item:
                inv_sku = f"CAP-450V-{secrets.token_hex(2)}"
                inv_item = InventoryItem(
                    branch_id=branch_id,
                    name="100uF 450V Electrolytic Capacitor",
                    sku=inv_sku,
                    barcode=f"BAR-{inv_sku}",
                    category="Capacitors",
                    unit="PCS",
                    min_stock_level=10.0,
                    cost_price=150.0,
                    retail_price=320.0,
                )
                db.add(inv_item)
                await db.flush()

                # Add initial stock ledger movement
                ledger_entry = StockLedger(
                    branch_id=branch_id,
                    inventory_item_id=inv_item.id,
                    movement_type="opening_stock",
                    quantity_change=45.0,
                    unit_cost=150.0,
                    total_cost=6750.0,
                    notes="Phase 9 initial stock balance",
                )
                db.add(ledger_entry)

            # 4. Client & Ticket for revenue & orders
            cl_res = await db.execute(select(Client).limit(1))
            test_client = cl_res.scalar_one_or_none()
            if not test_client:
                test_client = Client(
                    name="Precision Tooling Ltd",
                    phone="9820099881",
                    email="precision@tooling.in",
                    client_type="corporate",
                )
                db.add(test_client)
                await db.flush()

            ast_res = await db.execute(select(Asset).limit(1))
            test_asset = ast_res.scalar_one_or_none()
            if not test_asset:
                test_asset = Asset(
                    client_id=test_client.id,
                    name="CNC Spindle Inverter",
                    brand="Delta",
                    model="VFD-E Series",
                    asset_type="industrial_drive",
                    identifier="SN-DELTA-7890",
                )
                db.add(test_asset)
                await db.flush()

            t_res = await db.execute(select(Ticket).limit(1))
            test_ticket = t_res.scalar_one_or_none()
            if not test_ticket:
                test_ticket = Ticket(
                    ticket_number=f"TK-P9-{secrets.token_hex(3).upper()}",
                    branch_id=branch_id,
                    client_id=test_client.id,
                    asset_id=test_asset.id,
                    assigned_technician_id=tech_user.id,
                    status="repaired",
                    priority="high",
                    total_amount=12500.0,
                    advance_amount=2500.0,
                    balance_amount=10000.0,
                    problem_description="Short circuit on IGBT gate driver module",
                )
                db.add(test_ticket)
                await db.flush()

            # Add part to ticket
            tp_res = await db.execute(select(TicketPart).where(TicketPart.ticket_id == test_ticket.id).limit(1))
            if not tp_res.scalar_one_or_none():
                t_part = TicketPart(
                    ticket_id=test_ticket.id,
                    inventory_item_id=inv_item.id,
                    quantity=2.0,
                    unit_cost=inv_item.cost_price,
                    unit_price=inv_item.retail_price,
                    total_price=640.0,
                )
                db.add(t_part)

            # Add labor to ticket
            tl_res = await db.execute(select(TicketLabor).where(TicketLabor.ticket_id == test_ticket.id).limit(1))
            if not tl_res.scalar_one_or_none():
                t_labor = TicketLabor(
                    ticket_id=test_ticket.id,
                    assigned_tech_id=tech_user.id,
                    name="IGBT Module SMD Rework & Thermal Paste Replenishment",
                    labor_price=2800.0,
                    total_price=2800.0,
                    commission_rate=15.0,
                    commission_amount=420.0,
                )
                db.add(t_labor)

            # Add payment transaction
            pt_res = await db.execute(select(PaymentTransaction).where(PaymentTransaction.ticket_id == test_ticket.id).limit(1))
            if not pt_res.scalar_one_or_none():
                pay_txn = PaymentTransaction(
                    branch_id=branch_id,
                    ticket_id=test_ticket.id,
                    client_id=test_client.id,
                    amount=2500.0,
                    payment_method="upi",
                    upi_vpa="omnisuite@icici",
                    upi_intent_url="upi://pay?pa=omnisuite@icici&am=2500.00",
                    status="success",
                    transaction_ref=f"UPI-TXN-{secrets.token_hex(4).upper()}",
                )
                db.add(pay_txn)

            await db.commit()

        # Generate tokens
        owner_token = create_access_token(
            subject=owner_user.id,
            claims={"role": owner_user.role.slug if owner_user.role else "owner", "branch_id": str(branch_id)}
        )
        tech_token = create_access_token(
            subject=tech_user.id,
            claims={"role": tech_user.role.slug if tech_user.role else "technician", "branch_id": str(branch_id)}
        )

        owner_headers = {"Authorization": f"Bearer {owner_token}", "X-Branch-Id": str(branch_id)}
        tech_headers = {"Authorization": f"Bearer {tech_token}", "X-Branch-Id": str(branch_id)}

        # ----------------------------------------------------
        # TEST 1: Service Unit Tests - AnalyticsService
        # ----------------------------------------------------
        print("\n🔹 [TEST 1] Testing AnalyticsService direct aggregation...")
        async with AsyncSessionLocal() as db:
            summary = await AnalyticsService.get_company_summary(
                db=db,
                current_user=owner_user,
                branch_id=branch_id,
            )
            assert summary.currency == "INR"
            assert len(summary.kpi_cards) >= 4
            assert summary.ticket_velocity.intake_count >= 1
            print(f"  ✓ Company Summary aggregation passed: Revenue={summary.total_revenue}, Profit={summary.total_order_profit}")

            # Technician role scoping
            tech_summary = await AnalyticsService.get_company_summary(
                db=db,
                current_user=tech_user,
                branch_id=branch_id,
            )
            assert tech_summary.role == "technician"
            print("  ✓ Technician role scoping enforced in analytics summary")

            # Realtime Trends
            trends = await AnalyticsService.get_realtime_trends(
                db=db,
                current_user=owner_user,
                branch_id=branch_id,
                days=14,
            )
            assert len(trends.time_series) == 14
            assert len(trends.revenue_by_category) > 0
            assert len(trends.payment_methods_share) > 0
            print(f"  ✓ Realtime Trends calculated: {len(trends.time_series)} daily points")

        # ----------------------------------------------------
        # TEST 2: Service Unit Tests - ReportsService Catalog & Data (18+ Reports)
        # ----------------------------------------------------
        print("\n🔹 [TEST 2] Testing ReportsService 18+ Catalog & Data Generation...")
        catalog = ReportsService.get_catalog()
        assert len(catalog) >= 18, f"Expected 18+ reports, got {len(catalog)}"
        print(f"  ✓ Catalog loaded: {len(catalog)} reports registered")

        async with AsyncSessionLocal() as db:
            for rep in catalog:
                rtype = rep.report_type
                data = await ReportsService.generate_report(
                    db=db,
                    report_type=rtype,
                    current_user=owner_user,
                    branch_id=branch_id,
                )
                assert data.metadata.report_type == rtype
                assert isinstance(data.rows, list)
                assert isinstance(data.summary_totals, dict)
                assert isinstance(data.chart_data, list)
                print(f"    - Report '{rtype}': {len(data.rows)} rows, chart={len(data.chart_data)} items")

        print("  ✓ All 18+ reports verified for schema conformity and data generation!")

        # ----------------------------------------------------
        # TEST 3: Export Engine (CSV, Excel, PDF/HTML)
        # ----------------------------------------------------
        print("\n🔹 [TEST 3] Testing Export Engine (CSV, Excel, PDF)...")
        async with AsyncSessionLocal() as db:
            # 1. CSV
            csv_fn, csv_mime, csv_bytes = await ReportsService.export_report(
                db, "income_expense", export_format="csv", current_user=owner_user, branch_id=branch_id
            )
            assert csv_mime == "text/csv"
            assert len(csv_bytes) > 50
            print(f"  ✓ CSV Export generated: {csv_fn} ({len(csv_bytes)} bytes)")

            # 2. Excel
            xls_fn, xls_mime, xls_bytes = await ReportsService.export_report(
                db, "stock_valuation", export_format="excel", current_user=owner_user, branch_id=branch_id
            )
            assert "ms-excel" in xls_mime or "spreadsheet" in xls_mime or "csv" in xls_mime
            assert len(xls_bytes) > 50
            print(f"  ✓ Excel Export generated: {xls_fn} ({len(xls_bytes)} bytes)")

            # 3. PDF/HTML
            pdf_fn, pdf_mime, pdf_bytes = await ReportsService.export_report(
                db, "sla_on_time", export_format="pdf", current_user=owner_user, branch_id=branch_id
            )
            assert "html" in pdf_mime or "pdf" in pdf_mime
            assert len(pdf_bytes) > 100
            print(f"  ✓ PDF/HTML Export generated: {pdf_fn} ({len(pdf_bytes)} bytes)")

        # ----------------------------------------------------
        # TEST 4: Scheduled Reports DB Model & Auto-Dispatch
        # ----------------------------------------------------
        print("\n🔹 [TEST 4] Testing Scheduled Reports CRUD & Auto-Dispatch...")
        async with AsyncSessionLocal() as db:
            # Create schedule
            sch = ScheduledReport(
                branch_id=branch_id,
                created_by_id=owner_user.id,
                report_type="income_expense",
                title="Weekly Financial Executive Digest",
                frequency="weekly",
                export_format="pdf",
                recipients=["cfo@omnisuite.in", "director@omnisuite.in"],
                filters={"branch_id": str(branch_id)},
            )
            db.add(sch)
            await db.commit()
            await db.refresh(sch)
            assert sch.id is not None
            print(f"  ✓ Created ScheduledReport: id={sch.id}")

            # Dispatch scheduled reports
            dispatch_res = await ReportsService.dispatch_scheduled_reports(db)
            assert dispatch_res["dispatched"] >= 1
            print(f"  ✓ Dispatched scheduled reports: {dispatch_res['dispatched']} sent successfully")

            # Clean up test schedule
            await db.delete(sch)
            await db.commit()
            print("  ✓ Cleaned up test schedule successfully")

        # ----------------------------------------------------
        # TEST 5: HTTP API Endpoints via FastAPI Test Client
        # ----------------------------------------------------
        print("\n🔹 [TEST 5] Testing HTTP API Endpoints...")

        # 1. GET /analytics/summary
        r = await client.get("/api/v1/analytics/summary", headers=owner_headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        sum_body = r.json()
        assert sum_body["total_revenue"] >= 0
        assert len(sum_body["kpi_cards"]) >= 4
        print("  ✓ GET /api/v1/analytics/summary -> 200 OK")

        # 2. GET /analytics/trends
        r = await client.get("/api/v1/analytics/trends?days=14", headers=owner_headers)
        assert r.status_code == 200
        tr_body = r.json()
        assert len(tr_body["time_series"]) == 14
        print("  ✓ GET /api/v1/analytics/trends -> 200 OK")

        # 3. GET /reports/catalog
        r = await client.get("/api/v1/reports/catalog", headers=owner_headers)
        assert r.status_code == 200
        cat_body = r.json()
        assert len(cat_body) >= 18
        print(f"  ✓ GET /api/v1/reports/catalog -> 200 OK ({len(cat_body)} reports)")

        # 4. GET /reports/data/{report_type}
        r = await client.get("/api/v1/reports/data/stock_valuation", headers=owner_headers)
        assert r.status_code == 200
        rep_body = r.json()
        assert rep_body["metadata"]["report_type"] == "stock_valuation"
        print("  ✓ GET /api/v1/reports/data/stock_valuation -> 200 OK")

        # 5. GET /reports/export/{report_type}?format=csv
        r = await client.get("/api/v1/reports/export/income_expense?format=csv", headers=owner_headers)
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        print("  ✓ GET /api/v1/reports/export/income_expense?format=csv -> 200 OK")

        # 6. GET /reports/export/{report_type}?format=excel
        r = await client.get("/api/v1/reports/export/stock_valuation?format=excel", headers=owner_headers)
        assert r.status_code == 200
        assert "ms-excel" in r.headers["content-type"] or "spreadsheet" in r.headers["content-type"]
        print("  ✓ GET /api/v1/reports/export/stock_valuation?format=excel -> 200 OK")

        # 7. GET /reports/export/{report_type}?format=pdf
        r = await client.get("/api/v1/reports/export/sla_on_time?format=pdf", headers=owner_headers)
        assert r.status_code == 200
        assert "html" in r.headers["content-type"] or "pdf" in r.headers["content-type"]
        print("  ✓ GET /api/v1/reports/export/sla_on_time?format=pdf -> 200 OK")

        # 8. POST & GET /reports/scheduled
        sched_payload = {
            "report_type": "sales_profit",
            "title": "Daily Retail Margin Digest",
            "frequency": "daily",
            "export_format": "excel",
            "recipients": ["sales_mgr@omnisuite.in"],
            "filters": {"branch_id": str(branch_id)},
        }
        r = await client.post("/api/v1/reports/scheduled", json=sched_payload, headers=owner_headers)
        assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
        created_sched = r.json()
        created_id = created_sched["id"]
        print(f"  ✓ POST /api/v1/reports/scheduled -> 201 Created (id={created_id})")

        r = await client.get("/api/v1/reports/scheduled", headers=owner_headers)
        assert r.status_code == 200
        assert any(x["id"] == created_id for x in r.json())
        print("  ✓ GET /api/v1/reports/scheduled -> 200 OK")

        # 9. POST /reports/scheduled/run-dispatch
        r = await client.post("/api/v1/reports/scheduled/run-dispatch", headers=owner_headers)
        assert r.status_code == 200
        dispatch_res = r.json()
        assert dispatch_res["dispatched"] >= 1
        print("  ✓ POST /api/v1/reports/scheduled/run-dispatch -> 200 OK")

        # 10. DELETE /reports/scheduled/{id}
        r = await client.delete(f"/api/v1/reports/scheduled/{created_id}", headers=owner_headers)
        assert r.status_code == 200
        print(f"  ✓ DELETE /api/v1/reports/scheduled/{created_id} -> 200 OK")

    print("\n==================================================")
    print("🎉 ALL PHASE 9 BACKEND & INTEGRATION TESTS PASSED PERFECTLY!")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_phase9_tests())
