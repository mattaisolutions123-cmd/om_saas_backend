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
from app.models.ticket import Ticket, TicketPart, TicketLabor, TicketMedia, TicketEstimate
from app.models.notification import NotificationTemplate, NotificationOptOut, NotificationLog
from app.models.payment_transaction import PaymentTransaction
from app.models.feedback import CustomerFeedback
from app.models.automation import AutomationRule, ScheduledJob, MarketingCampaign
from app.services.notification_service import NotificationService
from app.services.automation_service import AutomationService
from app.core.security import create_access_token
from app.models.base import utc_now, to_utc
from sqlalchemy import select


async def run_phase8_tests():
    print("==================================================")
    print("🚀 STARTING PHASE 8 PUBLIC TRACKING, NOTIFICATIONS & AUTOMATION SUITE")
    print("==================================================")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Step 0: Ensure base test data
        async with AsyncSessionLocal() as db:
            # 1. Branch
            b_res = await db.execute(select(Branch).limit(1))
            branch = b_res.scalar_one_or_none()
            if not branch:
                branch = Branch(name="OmniSuite Tech Lab Mumbai", code="BR-MUM-P8", state_code="27", currency="INR")
                db.add(branch)
                await db.flush()
            branch_id = branch.id

            # 2. User (Manager)
            u_res = await db.execute(select(User).limit(1))
            manager = u_res.scalar_one()
            manager_id = manager.id

            # 3. Client & Asset
            test_phone = f"98200{secrets.token_hex(2)}"
            test_client = Client(
                name="Suresh Kumar Industries",
                phone="9820012345",
                email="suresh@kumarindustries.in",
                client_type="corporate",
                branch_id=branch_id,
            )
            db.add(test_client)
            await db.flush()

            test_asset = Asset(
                client_id=test_client.id,
                branch_id=branch_id,
                name="5HP Heavy Induction Motor",
                brand="Kirloskar",
                model="5HP-IND-MTR",
                asset_type="motor",
                identifier="KIR-IND-2026-9921",
            )
            db.add(test_asset)
            await db.flush()

            # 4. Work Order Ticket with Estimate & Media
            ticket_num = f"TK-202611-P8-{secrets.token_hex(3).upper()}"
            tracking_tok = secrets.token_hex(16)
            test_ticket = Ticket(
                ticket_number=ticket_num,
                branch_id=branch_id,
                client_id=test_client.id,
                asset_id=test_asset.id,
                ticket_type="service",
                status="waiting_approval",
                priority="high",
                assigned_tech_id=manager_id,
                created_by_id=manager_id,
                problem_reported="Excessive rotor vibration and bearing grinding noise under load",
                diagnosis_notes="Primary DE bearing race worn; rotor shaft requires 0.05mm lathe re-truing",
                qa_status="pending",
                promised_delivery_date=utc_now() + timedelta(days=3),
                customer_max_repair_budget=8000.0,
                advance_deposit=1500.0,
                total_parts_cost=2400.0,
                total_labor_cost=1800.0,
                tax_total=756.0,
                discount_amount=200.0,
                grand_total=4756.0,
                paid_amount=1500.0,
                balance_due=3256.0,
                is_paused=True,
                pause_reason="Awaiting customer estimate approval (exceeds standard threshold)",
                tracking_token=tracking_tok,
            )
            db.add(test_ticket)
            await db.flush()

            # Add Estimate
            est_token = secrets.token_hex(16)
            estimate = TicketEstimate(
                ticket_id=test_ticket.id,
                estimate_number=f"EST-{ticket_num}",
                approval_token=est_token,
                approval_status="pending",
                parts_subtotal=2400.0,
                labor_subtotal=1800.0,
                tax_total=756.0,
                grand_total=4756.0,
                line_items=[
                    {"description": "SKF Heavy Duty Roller Bearing 6308", "type": "part", "quantity": 2, "unit_price": 1200.0, "total_price": 2400.0},
                    {"description": "Lathe Machining & Dynamic Rotor Balancing", "type": "labor", "quantity": 1, "unit_price": 1800.0, "total_price": 1800.0},
                ],
                customer_notes="High precision bearing replacement + dynamic balancing",
                expires_at=utc_now() + timedelta(days=7),
            )
            db.add(estimate)

            # Add Inspection Photos
            photo1 = TicketMedia(
                ticket_id=test_ticket.id,
                media_type="before",
                file_url="https://images.unsplash.com/photo-1581092335397-9583fe92d232?w=600",
                file_name="intake_rotor_inspection.jpg",
                notes="Intake condition: heavy oxidation on bearing collar",
            )
            photo2 = TicketMedia(
                ticket_id=test_ticket.id,
                media_type="diagnostic_proof",
                file_url="https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=600",
                file_name="dial_gauge_runout_test.jpg",
                notes="Dial indicator confirms 0.08mm shaft eccentricity",
            )
            db.add_all([photo1, photo2])
            await db.commit()

        # Admin Auth Headers
        token = create_access_token(subject=manager_id, claims={"email": manager.email, "role": "manager", "branch_id": branch_id})
        headers = {"Authorization": f"Bearer {token}"}

        # ----------------------------------------------------
        # TEST 1: Public Tracking Endpoint GET /public/track/{token} (Zero Auth & Safe Fields)
        # ----------------------------------------------------
        print("\nTEST 1: Testing Public Tracking Endpoint GET /public/track/{token} (Zero Auth)...")
        r1 = await client.get(f"/public/track/{tracking_tok}")
        assert r1.status_code == 200, f"Public tracking failed: {r1.text}"
        track_data = r1.json()

        assert track_data["ticket_number"] == ticket_num
        assert track_data["current_stage"] == "Diagnosis"
        assert track_data["stage_index"] == 1
        assert track_data["progress_percentage"] == 40
        assert len(track_data["stages"]) == 5

        # Check confidential info is stripped and phone is masked
        assert track_data["client"]["phone_masked"].count("*") >= 2
        assert track_data["asset"]["brand"] == "Kirloskar"
        assert "SKF" in track_data["estimate"]["line_items"][0]["description"]
        assert len(track_data["photos"]) >= 2
        print(f"✅ Public Tracking Verified: Stage={track_data['current_stage']} ({track_data['progress_percentage']}%) | Masked Phone={track_data['client']['phone_masked']}")

        # ----------------------------------------------------
        # TEST 2: Customer Estimate Approval via Token
        # ----------------------------------------------------
        print("\nTEST 2: Testing Customer 1-Click Estimate Approval...")
        r2 = await client.post(
            f"/public/track/{tracking_tok}/estimate/approve",
            json={"customer_notes": "Approved proceed with SKF bearings"},
        )
        assert r2.status_code == 200, f"Estimate approval failed: {r2.text}"
        approve_data = r2.json()
        assert approve_data["approval_status"] == "approved"

        # Verify ticket unpaused & status updated to in_progress
        async with AsyncSessionLocal() as db:
            t_chk = (await db.execute(select(Ticket).where(Ticket.tracking_token == tracking_tok))).scalar_one()
            assert t_chk.is_paused == False
            assert t_chk.status == "in_progress"
        print(f"✅ Estimate Approved: Status=approved | Ticket Unpaused & Resumed: status={t_chk.status}")

        # ----------------------------------------------------
        # TEST 3: Customer Estimate Rejection via Token
        # ----------------------------------------------------
        print("\nTEST 3: Testing Customer Estimate Rejection...")
        # Create a second ticket to test rejection
        async with AsyncSessionLocal() as db:
            rej_tracking_tok = secrets.token_hex(16)
            rej_ticket = Ticket(
                ticket_number=f"TK-REJ-{secrets.token_hex(3).upper()}",
                branch_id=branch_id,
                client_id=test_client.id,
                ticket_type="service",
                status="waiting_approval",
                tracking_token=rej_tracking_tok,
            )
            db.add(rej_ticket)
            await db.flush()

            rej_estimate = TicketEstimate(
                ticket_id=rej_ticket.id,
                estimate_number=f"EST-REJ-{rej_ticket.ticket_number}",
                approval_token=secrets.token_hex(16),
                approval_status="pending",
                grand_total=12000.0,
            )
            db.add(rej_estimate)
            await db.commit()

        r3 = await client.post(
            f"/public/track/{rej_tracking_tok}/estimate/reject",
            json={"rejection_reason": "Cost exceeds our repair budget, please re-quote with refurbished part"},
        )
        assert r3.status_code == 200, f"Estimate rejection failed: {r3.text}"
        rej_data = r3.json()
        assert rej_data["approval_status"] == "rejected"
        assert "exceeds our repair budget" in rej_data["rejection_reason"]
        print(f"✅ Estimate Rejection Verified: Status=rejected | Reason Logged")

        # ----------------------------------------------------
        # TEST 4: Online UPI Payment Initiation
        # ----------------------------------------------------
        print("\nTEST 4: Testing Online UPI Payment Initiation...")
        r4 = await client.post(
            f"/public/track/{tracking_tok}/pay/upi",
            json={"amount": 3256.0, "notes": "Online UPI advance settlement"},
        )
        assert r4.status_code == 200, f"UPI payment initiation failed: {r4.text}"
        upi_res = r4.json()

        assert upi_res["amount"] == 3256.0
        assert upi_res["upi_vpa"] == "omnisuite@icici"
        assert "upi://pay?" in upi_res["upi_intent_url"]
        assert "pa=omnisuite%40icici" in upi_res["upi_intent_url"] or "pa=omnisuite@icici" in upi_res["upi_intent_url"]
        assert "gpay" in upi_res["payment_links"]
        assert "phonepe" in upi_res["payment_links"]
        assert "paytm" in upi_res["payment_links"]
        print(f"✅ UPI Intent Generated: Ref={upi_res['transaction_ref']} | URL={upi_res['upi_intent_url']}")

        # ----------------------------------------------------
        # TEST 5: Customer Feedback Submission
        # ----------------------------------------------------
        print("\nTEST 5: Testing Customer Feedback & NPS Submission...")
        r5 = await client.post(
            f"/public/track/{tracking_tok}/feedback",
            json={
                "overall_rating": 5,
                "technician_rating": 5,
                "nps_score": 10,
                "turnaround_satisfaction": "very_fast",
                "pricing_satisfaction": "good_value",
                "comments": "Exceptional precision lathe alignment. Vibration is completely gone!",
                "recommend_to_others": True,
            },
        )
        assert r5.status_code == 200, f"Feedback submission failed: {r5.text}"
        fb_res = r5.json()
        assert fb_res["success"] == True
        assert fb_res["overall_rating"] == 5
        print(f"✅ Feedback Submitted: Rating=5/5 | NPS=10 | Message: {fb_res['message']}")

        # ----------------------------------------------------
        # TEST 6: Notification Templates & Seeding
        # ----------------------------------------------------
        print("\nTEST 6: Testing Notification Templates Engine...")
        r6 = await client.get(f"/api/v1/notifications/templates?branch_id={branch_id}", headers=headers)
        assert r6.status_code == 200
        templates = r6.json()
        assert len(templates) >= 6
        tmpl_names = [t["name"] for t in templates]
        assert "feedback_survey_24h" in tmpl_names
        assert "maintenance_reminder_6m" in tmpl_names
        assert "warranty_expiry_15d" in tmpl_names
        assert "seasonal_campaign" in tmpl_names
        print(f"✅ Notification Templates Verified: {len(templates)} templates loaded ({', '.join(tmpl_names[:4])}...)")

        # ----------------------------------------------------
        # TEST 7: DLT / TRAI Opt-Out Registry Compliance
        # ----------------------------------------------------
        print("\nTEST 7: Testing DLT / TRAI Opt-Out Registry Enforcement...")
        opt_phone = "9820099999"
        # Register opt-out
        r7_opt = await client.post(
            "/api/v1/notifications/opt-outs",
            headers=headers,
            json={"phone": opt_phone, "channel": "all", "reason": "TRAI NDNC Scrub"},
        )
        assert r7_opt.status_code == 200

        # Attempt to dispatch promotional message to opted-out phone
        async with AsyncSessionLocal() as db:
            log_opt = await NotificationService.dispatch(
                db,
                channel="whatsapp",
                recipient_phone=opt_phone,
                template_name="seasonal_campaign",
                category="campaign",
                branch_id=branch_id,
            )
            assert log_opt.status == "opted_out"
            assert "TRAI/DLT NDNC Opt-Out" in log_opt.error_reason
        print(f"✅ TRAI Compliance Verified: Blocked message to {opt_phone} with status='opted_out'")

        # ----------------------------------------------------
        # TEST 8: Delivery Logging & Short-Link Click Tracking
        # ----------------------------------------------------
        print("\nTEST 8: Testing Notification Delivery & Click Tracking...")
        async with AsyncSessionLocal() as db:
            log_deliv = await NotificationService.dispatch(
                db,
                channel="whatsapp",
                recipient_phone="9820011223",
                template_name="ticket_intake",
                variables={"client_name": "Ramesh K.", "brand": "Kirloskar", "model": "Pump", "branch_name": "Mumbai Hub", "ticket_number": ticket_num},
                category="service_transactional",
                target_tracking_url=f"http://test/track/{tracking_tok}",
            )
            assert log_deliv.status == "delivered"
            short_token = log_deliv.click_token
            assert short_token is not None

        # Simulate customer clicking the short link GET /public/c/{token}
        r8_click = await client.get(f"/public/c/{short_token}", follow_redirects=False)
        assert r8_click.status_code == 302
        assert f"/track/{tracking_tok}" in r8_click.headers.get("location", "")

        # Verify click count incremented
        async with AsyncSessionLocal() as db:
            log_refreshed = (await db.execute(select(NotificationLog).where(NotificationLog.click_token == short_token))).scalar_one()
            assert log_refreshed.click_count >= 1
            assert log_refreshed.clicked_at is not None
        print(f"✅ Click Tracking Verified: Short Code={short_token} | Clicks={log_refreshed.click_count} | Redirected to {log_refreshed.click_target_url}")

        # ----------------------------------------------------
        # TEST 9: Automation Scheduler - Ticket Delivered Event Hook
        # ----------------------------------------------------
        print("\nTEST 9: Testing Automated Job Scheduling on Ticket Delivery...")
        async with AsyncSessionLocal() as db:
            t_deliv = (await db.execute(select(Ticket).where(Ticket.tracking_token == tracking_tok))).scalar_one()
            await AutomationService.schedule_ticket_delivery_automations(db, t_deliv)

            # Check that scheduled jobs were generated
            jobs_res = await db.execute(select(ScheduledJob).where(ScheduledJob.ticket_id == t_deliv.id))
            scheduled_jobs = jobs_res.scalars().all()
            job_types = [j.job_type for j in scheduled_jobs]
            assert "feedback_survey_24h" in job_types
            assert "maintenance_reminder_6m" in job_types
            assert "warranty_expiry_15d" in job_types

            # Verify 24h timing
            fb_job = next(j for j in scheduled_jobs if j.job_type == "feedback_survey_24h")
            assert to_utc(fb_job.scheduled_for) > utc_now() + timedelta(hours=20)
            assert to_utc(fb_job.scheduled_for) <= utc_now() + timedelta(hours=25)

            # Verify 6m timing (~180 days)
            maint_job = next(j for j in scheduled_jobs if j.job_type == "maintenance_reminder_6m")
            assert to_utc(maint_job.scheduled_for) > utc_now() + timedelta(days=170)
        print(f"✅ Delivery Automations Scheduled: Feedback (24h) | Maintenance (6m/180d) | Warranty Expiry (15d prior)")

        # ----------------------------------------------------
        # TEST 10: Automation Sweep Execution (POST /api/v1/automation/run-check)
        # ----------------------------------------------------
        print("\nTEST 10: Testing Automation Sweep Engine Execution...")
        # Create a job that is already due (scheduled_for in past)
        async with AsyncSessionLocal() as db:
            due_job = ScheduledJob(
                ticket_id=test_ticket.id,
                client_id=test_client.id,
                job_type="feedback_survey_24h",
                scheduled_for=utc_now() - timedelta(minutes=10),  # Due now!
                status="scheduled",
            )
            db.add(due_job)
            await db.commit()
            due_job_id = due_job.id

        r10 = await client.post("/api/v1/automation/run-check", headers=headers)
        assert r10.status_code == 200, f"Run check failed: {r10.text}"
        sweep_data = r10.json()
        assert sweep_data["processed_count"] >= 1
        assert sweep_data["executed_count"] >= 1

        async with AsyncSessionLocal() as db:
            chk_job = (await db.execute(select(ScheduledJob).where(ScheduledJob.id == due_job_id))).scalar_one()
            assert chk_job.status == "completed"
            assert chk_job.executed_at is not None
        print(f"✅ Automation Sweep Executed: Processed {sweep_data['processed_count']} jobs | Job status={chk_job.status}")

        # ----------------------------------------------------
        # TEST 11: Audience Segment Evaluation
        # ----------------------------------------------------
        print("\nTEST 11: Testing Customer Audience Segment Evaluation...")
        r11 = await client.post(
            "/api/v1/campaigns/segments/preview",
            headers=headers,
            json={"segment_type": "all", "segment_criteria": {}},
        )
        assert r11.status_code == 200, f"Segment preview failed: {r11.text}"
        seg_all = r11.json()
        assert seg_all["total_matches"] >= 1
        assert "eligible_count" in seg_all

        # High-value test
        r11_hv = await client.post(
            "/api/v1/campaigns/segments/preview",
            headers=headers,
            json={"segment_type": "high_value", "segment_criteria": {"min_spend": 1000.0}},
        )
        assert r11_hv.status_code == 200
        seg_hv = r11_hv.json()
        print(f"✅ Segment Evaluated: All Customers={seg_all['total_matches']} | High-Value Eligible={seg_hv['eligible_count']}")

        # ----------------------------------------------------
        # TEST 12: Campaign Builder & Broadcast Dispatch
        # ----------------------------------------------------
        print("\nTEST 12: Testing Campaign Builder & Broadcast Dispatch...")
        r12_create = await client.post(
            "/api/v1/campaigns",
            headers=headers,
            json={
                "branch_id": branch_id,
                "name": "Diwali Precision Maintenance Special",
                "channel": "whatsapp",
                "segment_type": "all",
                "custom_message": "Festive greeting from {{branch_name}}! 20% discount on motor balancing: {{tracking_url}}",
            },
        )
        assert r12_create.status_code == 200, f"Create campaign failed: {r12_create.text}"
        camp_data = r12_create.json()
        campaign_id = camp_data["id"]

        # Send broadcast
        r12_send = await client.post(f"/api/v1/campaigns/{campaign_id}/send", headers=headers)
        assert r12_send.status_code == 200, f"Campaign send failed: {r12_send.text}"
        send_summary = r12_send.json()
        assert send_summary["status"] == "completed"
        assert send_summary["sent_count"] >= 1
        print(f"✅ Campaign Broadcast Complete: Campaign='{send_summary['name']}' | Sent={send_summary['sent_count']} | Delivered={send_summary['delivered_count']}")

        # ----------------------------------------------------
        # TEST 13: Delivery Stats Aggregation
        # ----------------------------------------------------
        print("\nTEST 13: Testing Notification Analytics Stats Summary...")
        r13 = await client.get("/api/v1/notifications/stats", headers=headers)
        assert r13.status_code == 200
        stats = r13.json()
        assert stats["total_dispatched"] >= 1
        assert "delivery_rate_percent" in stats
        assert "by_channel" in stats
        print(f"✅ Stats Aggregated: Dispatched={stats['total_dispatched']} | Delivery Rate={stats['delivery_rate_percent']}% | Opt-Outs={stats['total_opted_out']}")

        print("\n==================================================")
        print("🎉 ALL 13 PHASE 8 BACKEND TESTS PASSED SUCCESSFULLY!")
        print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_phase8_tests())
