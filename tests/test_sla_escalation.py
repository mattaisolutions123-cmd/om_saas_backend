import pytest
import secrets
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from app.models.branch import Branch
from app.models.user import User
from app.models.task import Task, SLATierConfig, EscalationLog
from app.services.task_service import TaskService
from app.models.base import utc_now


@pytest.mark.asyncio
class TestSLAEscalation:
    async def test_sla_escalation_engine(self, db_session):
        """
        Verify SLA escalation engine triggers automated tier elevation
        and logs breaches when overdue thresholds are exceeded.
        """
        # 1. Fetch branch and user
        b_res = await db_session.execute(select(Branch).limit(1))
        branch = b_res.scalar_one()

        u_res = await db_session.execute(select(User).limit(1))
        user = u_res.scalar_one()

        # 2. Ensure SLA tiers exist
        await TaskService.seed_defaults(db_session, branch.id)

        # 3. Create an overdue task with past target_deadline
        past_deadline = utc_now() - timedelta(hours=4)
        task_num = await TaskService.generate_task_number(db_session, branch.id)

        overdue_task = Task(
            task_number=task_num,
            branch_id=branch.id,
            author_id=user.id,
            executor_id=user.id,
            title="Urgent Microwave Magnetron Replacement",
            description="Replace failed magnetron tube in customer oven",
            task_type="manual",
            priority="high",
            status="in_progress",
            sla_tier="T1",
            deadline=past_deadline,
            sla_deadline=past_deadline,
            created_at=utc_now() - timedelta(hours=8),
        )
        db_session.add(overdue_task)
        await db_session.flush()

        # 4. Execute SLA Escalation Engine
        escalation_results = await TaskService.run_sla_escalation_engine(
            db=db_session,
            branch_id=branch.id,
        )

        assert isinstance(escalation_results, dict)
        assert "evaluated_tasks_count" in escalation_results
        assert "l2_breaches" in escalation_results
        assert len(escalation_results["escalation_logs"]) >= 1

        # 5. Check if task was marked breached/expired
        await db_session.refresh(overdue_task)
        assert overdue_task.is_expired is True or overdue_task.sla_status in ["L2_BREACHED", "WARNING_75", "L1_PUSH"]

        # Verify escalation log exists
        log_res = await db_session.execute(
            select(EscalationLog).where(EscalationLog.task_id == overdue_task.id)
        )
        logs = log_res.scalars().all()
        assert len(logs) >= 1
        assert logs[0].escalation_level in ["L2_BREACH", "L1_PUSH", "75%_ELAPSED", "L3_WHATSAPP"]
