from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.db.session import get_db
from app.models.automation import AutomationRule, ScheduledJob
from app.schemas.automation import (
    AutomationRuleResponse,
    AutomationRuleUpdate,
    ScheduledJobResponse,
    RunAutomationResponse,
)
from app.services.automation_service import AutomationService

router = APIRouter(prefix="/automation", tags=["Automation Scheduler"])


@router.get("/rules", response_model=List[AutomationRuleResponse])
async def list_rules(
    branch_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    await AutomationService.ensure_default_rules(db, branch_id)
    stmt = select(AutomationRule).order_by(AutomationRule.created_at)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.put("/rules/{rule_id}", response_model=AutomationRuleResponse)
async def update_rule(
    rule_id: str,
    payload: AutomationRuleUpdate,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AutomationRule).where(AutomationRule.id == rule_id)
    res = await db.execute(stmt)
    rule = res.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Automation rule not found")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(rule, k, v)

    await db.commit()
    await db.refresh(rule)
    return rule


@router.get("/scheduled-jobs", response_model=List[ScheduledJobResponse])
async def list_scheduled_jobs(
    status: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ScheduledJob)
    if status:
        stmt = stmt.where(ScheduledJob.status == status)
    stmt = stmt.order_by(desc(ScheduledJob.scheduled_for)).limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/run-check", response_model=RunAutomationResponse)
async def trigger_automation_check(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Manually triggers execution of pending scheduled jobs
    (24h feedback surveys, 6m maintenance reminders, 15d warranty notices).
    """
    base_url = str(request.base_url).rstrip("/")
    # Replace test port or local backend port if running behind frontend
    return await AutomationService.run_automation_sweep(db, base_url=base_url)
