from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.api.v1.auth import get_current_user
from app.schemas.analytics import CompanySummaryResponse, TrendsResponse
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["Analytics & BI Engine"])


@router.get("/summary", response_model=CompanySummaryResponse)
async def get_company_summary(
    branch_id: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns consolidated executive KPI cards, turnover, order profit margins,
    ticket velocity ratio, technician commission totals, and stock valuation.
    Role-scoped:
    - Owner: global / all branches
    - Manager: scoped to branch
    - Cashier: scoped to register
    - Technician: scoped to own tickets & commission
    """
    return await AnalyticsService.get_company_summary(
        db=db,
        current_user=current_user,
        branch_id=branch_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/trends", response_model=TrendsResponse)
async def get_realtime_trends(
    branch_id: Optional[str] = Query(None),
    days: int = Query(14, ge=1, le=90),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns real-time daily time-series trends (revenue, expenses, net profit,
    ticket intake vs completed) and multi-branch comparative benchmarks.
    """
    return await AnalyticsService.get_realtime_trends(
        db=db,
        current_user=current_user,
        branch_id=branch_id,
        days=days,
    )
