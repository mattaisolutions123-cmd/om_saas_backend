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
from app.models.ticket import Ticket
from app.models.task import Task, SLATierConfig, EscalationLog, StatusTriggerRule
from app.services.task_service import TaskService
from app.core.security import create_access_token
from sqlalchemy import select


async def run_phase7_tests():
    print("==================================================")
    print("🚀 STARTING PHASE 7 TASKS, SMART WORKLOAD & SLA SUITE")
    print("==================================================")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Step 0: Ensure base test data
        async with AsyncSessionLocal() as db:
            # 1. Branch
            b_res = await db.execute(select(Branch).limit(1))
            branch = b_res.scalar_one_or_none()
            if not branch:
                branch = Branch(name="OmniSuite Tech Lab Mumbai", code="BR-MUM-P7", state_code="27", currency="INR")
                db.add(branch)
                await db.flush()
            branch_id = branch.id

            # 2. Users: Manager (author) and 2 Technicians (executors)
            mgr_res = await db.execute(select(User).where(User.email.like("%manager%")).limit(1))
            manager = mgr_res.scalar_one_or_none()
            if not manager:
                u_res = await db.execute(select(User).limit(1))
                manager = u_res.scalar_one()

            # Technician 1: Lathe specialist
            t1_res = await db.execute(select(User).where(User.email == "tech.lathe@omnisuite.in"))
            tech_lathe = t1_res.scalar_one_or_none()
            if not tech_lathe:
                tech_lathe = User(
                    email="tech.lathe@omnisuite.in",
                    hashed_password="hashed_pw_test",
                    full_name="Rajesh Lathe Expert",
                    phone="9820011223",
                    role_id=manager.role_id,
                    branch_id=branch_id,
                    preferences={"skills": ["Lathe", "Machining", "Workshop", "Turning"], "tech_score": 95.0},
                )
                db.add(tech_lathe)
                await db.flush()

            # Technician 2: Electronics / Micro-soldering
            t2_res = await db.execute(select(User).where(User.email == "tech.elec@omnisuite.in"))
            tech_elec = t2_res.scalar_one_or_none()
            if not tech_elec:
                tech_elec = User(
                    email="tech.elec@omnisuite.in",
                    hashed_password="hashed_pw_test",
                    full_name="Amit Micro Soldering",
                    phone="9820099887",
                    role_id=manager.role_id,
                    branch_id=branch_id,
                    preferences={"skills": ["Electronics", "BGA", "Diagnostics"], "tech_score": 90.0},
                )
                db.add(tech_elec)
                await db.flush()

            # 3. Client & Ticket for automated status-trigger testing
            c_res = await db.execute(select(Client).limit(1))
            test_client = c_res.scalar_one_or_none()
            if not test_client:
                test_client = Client(
                    name="Bharat Precision Tools",
                    phone="9876543210",
                    email="contact@bharattools.in",
                    client_type="corporate",
                    branch_id=branch_id,
                )
                db.add(test_client)
                await db.flush()

            ticket_num = f"TK-202611-P7-{secrets.token_hex(3).upper()}"
            test_ticket = Ticket(
                ticket_number=ticket_num,
                branch_id=branch_id,
                client_id=test_client.id,
                status="intake",
                priority="standard",
                assigned_tech_id=tech_lathe.id,
                created_by_id=manager.id,
                problem_reported="Spindle motor core burnt and uneven shaft rotation",
                tracking_token=secrets.token_hex(16),
            )
            db.add(test_ticket)
            await db.commit()

            manager_id = manager.id
            tech_lathe_id = tech_lathe.id
            tech_elec_id = tech_elec.id
            ticket_id = test_ticket.id
            tracking_tok = test_ticket.tracking_token

        token = create_access_token(subject=manager_id, claims={"email": manager.email, "role": "manager", "branch_id": branch_id})
        headers = {"Authorization": f"Bearer {token}"}

        # ----------------------------------------------------
        # TEST 1: Seed & Verify SLA Tier Configurations
        # ----------------------------------------------------
        print("\nTEST 1: Verifying SLA Tier Configs (T1 Emergency <4h, T2 High <24h with 2h diagnose, T3 Standard 3-7 days)...")
        r1 = await client.get("/api/v1/tasks/sla/tiers", headers=headers)
        assert r1.status_code == 200, f"Failed listing SLA tiers: {r1.text}"
        tiers = r1.json()
        assert len(tiers) >= 3, f"Expected at least 3 tiers, got {len(tiers)}"
        tier_codes = {t["tier_code"]: t for t in tiers}
        assert "T1" in tier_codes and tier_codes["T1"]["resolution_hours"] <= 4.0
        assert "T2" in tier_codes and tier_codes["T2"]["resolution_hours"] <= 24.0 and tier_codes["T2"]["diagnosis_hours"] == 2.0
        assert "T3" in tier_codes and tier_codes["T3"]["resolution_hours"] >= 72.0
        print(f"✅ SLA Tiers Verified: T1 ({tier_codes['T1']['resolution_hours']}h), T2 ({tier_codes['T2']['resolution_hours']}h / diag {tier_codes['T2']['diagnosis_hours']}h), T3 ({tier_codes['T3']['resolution_hours']}h)")

        # ----------------------------------------------------
        # TEST 2: Create Manual Task (Author vs Executor Segregation)
        # ----------------------------------------------------
        print("\nTEST 2: Creating Manual Task with Author vs Executor Segregation & Deadline...")
        task_payload = {
            "branch_id": branch_id,
            "author_id": manager_id,
            "executor_id": tech_elec_id,
            "title": "Perform spindle motor insulation diagnostic",
            "description": "High voltage insulation resistance test on 3-phase windings",
            "category": "Workshop",
            "priority": "high",
            "status": "Backlog",
            "sla_tier": "T2",
            "pin_code": "400001",
            "checklist": [
                {"id": "1", "text": "Inspect carbon brush seating", "completed": False},
                {"id": "2", "text": "Measure megger insulation resistance", "completed": False},
            ],
            "tags": ["diagnostics", "motor", "workshop"],
        }
        r2 = await client.post("/api/v1/tasks", json=task_payload, headers=headers)
        assert r2.status_code == 201, f"Task creation failed: {r2.text}"
        task_data = r2.json()
        task_id = task_data["id"]
        assert task_data["author_id"] == manager_id
        assert task_data["executor_id"] == tech_elec_id
        assert task_data["category"] == "Workshop"
        assert task_data["status"] == "Backlog"
        assert task_data["pin_code"] == "400001"
        assert len(task_data["checklist"]) == 2
        print(f"✅ Manual Task Created: {task_data['task_number']} - {task_data['title']} (Author: {task_data['author_name']}, Executor: {task_data['executor_name']})")

        # ----------------------------------------------------
        # TEST 3: Status Progression (Backlog -> In Progress -> Review -> Done)
        # ----------------------------------------------------
        print("\nTEST 3: Testing Task Status Progression: Backlog -> In Progress -> Review -> Done...")
        for target_status in ["In Progress", "Review", "Done"]:
            r3 = await client.put(f"/api/v1/tasks/{task_id}", json={"status": target_status}, headers=headers)
            assert r3.status_code == 200, f"Update status to {target_status} failed: {r3.text}"
            res3 = r3.json()
            assert res3["status"] == target_status
            if target_status == "Done":
                assert res3["completed_at"] is not None
        print(f"✅ Full Lifecycle Verified: Backlog ➔ In Progress ➔ Review ➔ Done (Completed At: {res3['completed_at']})")

        # ----------------------------------------------------
        # TEST 4: Smart Workload Balancing
        # ----------------------------------------------------
        print("\nTEST 4: Testing Smart Workload Balancing (Skills + Open Load + Score)...")
        r4 = await client.get(f"/api/v1/tasks/workload/balance?branch_id={branch_id}&category=Lathe", headers=headers)
        assert r4.status_code == 200, f"Workload balancing query failed: {r4.text}"
        wb_data = r4.json()
        assert len(wb_data["technicians"]) >= 2
        recommended = wb_data["recommended_technician"]
        assert recommended is not None
        assert "Lathe" in recommended["matched_skills"] or recommended["name"] == "Rajesh Lathe Expert"
        print(f"✅ Smart Workload Balancing Recommendation: {recommended['name']} (Score: {recommended['workload_score']}, Matched: {recommended['matched_skills']})")

        # ----------------------------------------------------
        # TEST 5: Status-Trigger Rules (Lathe Work -> Deliver core to lathe workshop)
        # ----------------------------------------------------
        print("\nTEST 5: Testing Ticket Status Trigger (Lathe Work -> Deliver core to lathe workshop)...")
        # Update ticket status to "Lathe Work"
        r5 = await client.put(f"/api/v1/tickets/{ticket_id}", json={"status": "Lathe Work"}, headers=headers)
        assert r5.status_code == 200, f"Ticket update to Lathe Work failed: {r5.text}"

        # Check automated task created
        r5_tasks = await client.get(f"/api/v1/tasks?ticket_id={ticket_id}", headers=headers)
        assert r5_tasks.status_code == 200
        t_list = r5_tasks.json()
        lathe_task = next((t for t in t_list if "lathe workshop" in t["title"].lower()), None)
        assert lathe_task is not None, f"Expected lathe workshop auto task, found: {t_list}"
        assert lathe_task["task_type"] == "auto-from-ticket-status"
        assert lathe_task["category"] == "Workshop"
        print(f"✅ Status-Trigger Task Created: {lathe_task['task_number']} - {lathe_task['title']} (Type: {lathe_task['task_type']})")

        # ----------------------------------------------------
        # TEST 6: Status-Trigger Rule (Spare Wait -> Source part)
        # ----------------------------------------------------
        print("\nTEST 6: Testing Ticket Status Trigger (Spare Wait -> Source part)...")
        r6 = await client.put(f"/api/v1/tickets/{ticket_id}", json={"status": "Spare Wait"}, headers=headers)
        assert r6.status_code == 200

        r6_tasks = await client.get(f"/api/v1/tasks?ticket_id={ticket_id}", headers=headers)
        spare_task = next((t for t in r6_tasks.json() if "source part" in t["title"].lower()), None)
        assert spare_task is not None, f"Expected 'Source part' auto task, found: {r6_tasks.json()}"
        assert spare_task["category"] == "Procurement"
        print(f"✅ Status-Trigger Task Created: {spare_task['task_number']} - {spare_task['title']} (Category: {spare_task['category']})")

        # ----------------------------------------------------
        # TEST 7: Status-Trigger Rule (Work Done -> Notify client for pickup)
        # ----------------------------------------------------
        print("\nTEST 7: Testing Ticket Status Trigger (Work Done -> Notify client for pickup)...")
        r7 = await client.put(f"/api/v1/tickets/{ticket_id}", json={"status": "Work Done"}, headers=headers)
        assert r7.status_code == 200

        r7_tasks = await client.get(f"/api/v1/tasks?ticket_id={ticket_id}", headers=headers)
        done_task = next((t for t in r7_tasks.json() if "notify client" in t["title"].lower()), None)
        assert done_task is not None, f"Expected 'Notify client for pickup' auto task, found: {r7_tasks.json()}"
        assert done_task["category"] == "Customer Communication"
        print(f"✅ Status-Trigger Task Created: {done_task['task_number']} - {done_task['title']} (Category: {done_task['category']})")

        # ----------------------------------------------------
        # TEST 8: 75% Elapsed SLA Escalation (URGENT Flag)
        # ----------------------------------------------------
        print("\nTEST 8: Testing 75% Elapsed SLA Warning (URGENT flag + High Priority)...")
        # Create a task where 80% time has elapsed: started 24h ago, deadline 6h from now (total 30h)
        # Remaining hours = 6h (> 4h L1 threshold, but >= 75% elapsed)
        now = datetime.now(timezone.utc)
        past_time = now - timedelta(hours=24)
        near_deadline = now + timedelta(hours=6)
        async with AsyncSessionLocal() as db:
            urgent_task = Task(
                task_number=await TaskService.generate_task_number(db, branch_id),
                branch_id=branch_id,
                author_id=manager_id,
                executor_id=tech_elec_id,
                title="Emergency BGA reballing on motherboard",
                category="Workshop",
                priority="standard",
                status="In Progress",
                created_at=past_time,
                deadline=near_deadline,
                is_urgent=False,
            )
            db.add(urgent_task)
            await db.commit()
            urgent_task_id = urgent_task.id

        # Run SLA Escalation check
        r8 = await client.post(f"/api/v1/tasks/sla/check-escalations?branch_id={branch_id}", headers=headers)
        assert r8.status_code == 200, f"Escalation run failed: {r8.text}"

        # Verify task is now URGENT
        r8_task = await client.get(f"/api/v1/tasks/{urgent_task_id}", headers=headers)
        u_data = r8_task.json()
        assert u_data["is_urgent"] is True
        assert u_data["priority"] in ["urgent", "high"]
        assert u_data["sla_status"] == "WARNING_75"
        print(f"✅ 75% Elapsed Escalation Triggered: Task {u_data['task_number']} flagged URGENT (Priority: {u_data['priority']}, Status: {u_data['sla_status']})")

        # ----------------------------------------------------
        # TEST 9: L1 Amber Push Warning (T-4h before breach)
        # ----------------------------------------------------
        print("\nTEST 9: Testing L1 Escalation (T-4h Push Amber Alert)...")
        # Task due in 2 hours
        async with AsyncSessionLocal() as db:
            l1_task = Task(
                task_number=await TaskService.generate_task_number(db, branch_id),
                branch_id=branch_id,
                author_id=manager_id,
                executor_id=tech_lathe_id,
                title="Final shaft balancing verification",
                category="Workshop",
                priority="high",
                status="In Progress",
                created_at=now - timedelta(hours=1),
                deadline=now + timedelta(hours=2),  # <= 4 hours remaining
                is_urgent=False,
                sla_status="OK",
            )
            db.add(l1_task)
            await db.commit()
            l1_task_id = l1_task.id

        r9 = await client.post(f"/api/v1/tasks/sla/check-escalations?branch_id={branch_id}", headers=headers)
        assert r9.status_code == 200

        r9_task = await client.get(f"/api/v1/tasks/{l1_task_id}", headers=headers)
        l1_data = r9_task.json()
        assert l1_data["sla_status"] == "L1_PUSH"
        print(f"✅ L1 Amber Push Engaged: Task {l1_data['task_number']} (SLA Status: {l1_data['sla_status']})")

        # ----------------------------------------------------
        # TEST 10: L2 Breach (EXPIRED, Overdue Counter, Manager Alert, Tech Penalty)
        # ----------------------------------------------------
        print("\nTEST 10: Testing L2 Breach (EXPIRED, Overdue Counter, Tech Penalty & Manager Alert)...")
        # Task with deadline 3 hours in the past
        past_deadline = now - timedelta(hours=3)
        async with AsyncSessionLocal() as db:
            breach_task = Task(
                task_number=await TaskService.generate_task_number(db, branch_id),
                branch_id=branch_id,
                author_id=manager_id,
                executor_id=tech_lathe_id,
                ticket_id=ticket_id,
                title="Unfinished armature rewinding job",
                category="Workshop",
                priority="high",
                status="In Progress",
                created_at=now - timedelta(hours=8),
                deadline=past_deadline,
                is_expired=False,
                sla_status="OK",
            )
            db.add(breach_task)
            await db.commit()
            breach_task_id = breach_task.id

        r10 = await client.post(f"/api/v1/tasks/sla/check-escalations?branch_id={branch_id}", headers=headers)
        assert r10.status_code == 200

        r10_task = await client.get(f"/api/v1/tasks/{breach_task_id}", headers=headers)
        b_data = r10_task.json()
        assert b_data["is_expired"] is True
        assert b_data["overdue_minutes"] >= 170  # ~180 mins overdue
        print(f"✅ L2 Breach Confirmed: Task {b_data['task_number']} EXPIRED by {b_data['overdue_minutes']} mins (SLA: {b_data['sla_status']})")

        # Verify escalation log for L2
        r10_logs = await client.get(f"/api/v1/tasks/sla/logs?branch_id={branch_id}&level=L2_BREACH", headers=headers)
        assert r10_logs.status_code == 200
        l2_logs = r10_logs.json()
        assert len(l2_logs) >= 1
        assert l2_logs[0]["penalty_applied"] > 0
        print(f"✅ L2 Manager Alert & Penalty Logged: -{l2_logs[0]['penalty_applied']} pts for {l2_logs[0]['tech_name']}")

        # ----------------------------------------------------
        # TEST 11: 1-Click Reassignment
        # ----------------------------------------------------
        print("\nTEST 11: Testing 1-Click Reassignment on Breached Task...")
        r11 = await client.post(
            f"/api/v1/tasks/{breach_task_id}/reassign",
            json={"new_executor_id": tech_elec_id, "reason": "L2 breach escalation: emergency reassignment to senior technician"},
            headers=headers,
        )
        assert r11.status_code == 200, f"Reassign failed: {r11.text}"
        reassigned_data = r11.json()
        assert reassigned_data["executor_id"] == tech_elec_id
        assert len(reassigned_data["task_metadata"].get("reassign_history", [])) >= 1
        print(f"✅ 1-Click Reassign Completed: Transferred from Rajesh to {reassigned_data['executor_name']}")

        # ----------------------------------------------------
        # TEST 12: L3 Customer Courtesy WhatsApp Message
        # ----------------------------------------------------
        print("\nTEST 12: Testing L3 Customer Courtesy WhatsApp Message Dispatch...")
        r12_logs = await client.get(f"/api/v1/tasks/sla/logs?branch_id={branch_id}&level=L3_WHATSAPP", headers=headers)
        assert r12_logs.status_code == 200
        wa_logs = r12_logs.json()
        assert len(wa_logs) >= 1, f"Expected L3 WhatsApp log, found: {wa_logs}"
        wa_payload = wa_logs[0]["whatsapp_payload"]
        assert "message_body" in wa_payload
        assert "track" in wa_payload["message_body"]
        print(f"✅ L3 Customer WhatsApp Courtesy Logged: To {wa_payload['client_name']} ({wa_payload['client_phone']})")

        # ----------------------------------------------------
        # TEST 13: L4 Monthly On-Time % Analytics
        # ----------------------------------------------------
        print("\nTEST 13: Testing L4 Monthly On-Time % Analytics Engine...")
        r13 = await client.get(f"/api/v1/tasks/sla/analytics?branch_id={branch_id}", headers=headers)
        assert r13.status_code == 200, f"Analytics failed: {r13.text}"
        analytics = r13.json()
        assert analytics["total_tasks"] >= 3
        assert "overall_on_time_percent" in analytics
        assert len(analytics["categories"]) >= 1
        assert len(analytics["technicians"]) >= 1
        print(f"✅ L4 Analytics Generated: Period {analytics['period_label']} | On-Time: {analytics['overall_on_time_percent']}% | Categories: {len(analytics['categories'])} | Techs: {len(analytics['technicians'])}")

        print("\n==================================================")
        print("🎉 ALL 13 PHASE 7 BACKEND TESTS PASSED SUCCESSFULLY!")
        print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_phase7_tests())
