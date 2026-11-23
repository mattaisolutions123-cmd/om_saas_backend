from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.db.session import get_db
from app.models.user import User
from app.models.scheduled_report import ScheduledReport
from app.api.v1.auth import get_current_user
from app.schemas.reports import (
    ReportMetadata,
    ReportDataResponse,
    ScheduledReportCreate,
    ScheduledReportUpdate,
    ScheduledReportResponse,
)
from app.services.reports_service import ReportsService

router = APIRouter(prefix="/reports", tags=["Reports & BI"])


# ============================================================
# 1. Report Catalog
# ============================================================
@router.get("/catalog", response_model=List[ReportMetadata])
async def get_reports_catalog():
    """Returns directory of all 18+ available financial, operational, and inventory reports."""
    return ReportsService.get_catalog()


# ============================================================
# 2. Query Specific Report Data
# ============================================================
@router.get("/data/{report_type}", response_model=ReportDataResponse)
async def query_report_data(
    report_type: str,
    branch_id: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Executes a standard report query with role scoping (Owner global, Manager branch, Tech own commission).
    """
    return await ReportsService.generate_report(
        db=db,
        report_type=report_type,
        current_user=current_user,
        branch_id=branch_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


# ============================================================
# 3. Export Report (CSV / Excel / PDF HTML)
# ============================================================
@router.get("/export/{report_type}")
async def export_report_file(
    report_type: str,
    format: str = Query("csv", pattern="^(csv|excel|pdf)$"),
    branch_id: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Exports report dataset directly to downloadable CSV, Excel spreadsheet, or printable HTML/PDF.
    """
    filename, media_type, content = await ReportsService.export_report(
        db=db,
        report_type=report_type,
        export_format=format,
        current_user=current_user,
        branch_id=branch_id,
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ============================================================
# 4. Scheduled Recurring Email Reports
# ============================================================
@router.get("/scheduled", response_model=List[ScheduledReportResponse])
@router.get("/scheduled/list", response_model=List[ScheduledReportResponse])
async def list_scheduled_reports(
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ScheduledReport)
    if branch_id:
        stmt = stmt.where(or_(ScheduledReport.branch_id == branch_id, ScheduledReport.branch_id == None))
    stmt = stmt.order_by(desc(ScheduledReport.created_at))
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/scheduled", response_model=ScheduledReportResponse, status_code=status.HTTP_201_CREATED)
async def create_scheduled_report(
    payload: ScheduledReportCreate,
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rep = ScheduledReport(
        branch_id=payload.branch_id,
        created_by_id=current_user.id if current_user else None,
        report_type=payload.report_type,
        title=payload.title,
        frequency=payload.frequency,
        export_format=payload.export_format,
        recipients=payload.recipients,
        filters=payload.filters,
        is_active=payload.is_active,
    )
    db.add(rep)
    await db.commit()
    await db.refresh(rep)
    return rep


@router.put("/scheduled/{report_id}", response_model=ScheduledReportResponse)
async def update_scheduled_report(
    report_id: str,
    payload: ScheduledReportUpdate,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ScheduledReport).where(ScheduledReport.id == report_id)
    res = await db.execute(stmt)
    rep = res.scalar_one_or_none()
    if not rep:
        raise HTTPException(status_code=404, detail="Scheduled report not found")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(rep, k, v)

    await db.commit()
    await db.refresh(rep)
    return rep


@router.delete("/scheduled/{report_id}")
async def delete_scheduled_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ScheduledReport).where(ScheduledReport.id == report_id)
    res = await db.execute(stmt)
    rep = res.scalar_one_or_none()
    if not rep:
        raise HTTPException(status_code=404, detail="Scheduled report not found")

    await db.delete(rep)
    await db.commit()
    return {"success": True, "message": "Scheduled report cancelled"}


@router.post("/scheduled/run-dispatch")
async def trigger_scheduled_dispatch(db: AsyncSession = Depends(get_db)):
    """Triggers automated execution and email dispatch for recurring scheduled reports."""
    return await ReportsService.dispatch_scheduled_reports(db)
