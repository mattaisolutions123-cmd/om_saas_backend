from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, desc

from app.db.session import get_db
from app.models.notification import NotificationTemplate, NotificationLog, NotificationOptOut
from app.schemas.notification import (
    NotificationTemplateCreate,
    NotificationTemplateUpdate,
    NotificationTemplateResponse,
    NotificationOptOutCreate,
    NotificationOptOutResponse,
    NotificationLogResponse,
    NotificationStatsResponse,
    SendManualNotificationRequest,
)
from app.services.notification_service import NotificationService
from app.models.base import utc_now

router = APIRouter(prefix="/notifications", tags=["Notifications & DLT Engine"])


# ============================================================
# Templates
# ============================================================
@router.get("/templates", response_model=List[NotificationTemplateResponse])
async def list_templates(
    channel: Optional[str] = None,
    category: Optional[str] = None,
    branch_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    await NotificationService.ensure_default_templates(db, branch_id)
    stmt = select(NotificationTemplate)
    if channel:
        stmt = stmt.where(NotificationTemplate.channel == channel)
    if category:
        stmt = stmt.where(NotificationTemplate.category == category)
    if branch_id:
        stmt = stmt.where(or_(NotificationTemplate.branch_id == branch_id, NotificationTemplate.branch_id == None))

    stmt = stmt.order_by(NotificationTemplate.name)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/templates", response_model=NotificationTemplateResponse)
async def create_template(
    payload: NotificationTemplateCreate,
    db: AsyncSession = Depends(get_db),
):
    tmpl = NotificationTemplate(
        branch_id=payload.branch_id,
        name=payload.name,
        channel=payload.channel,
        category=payload.category,
        dlt_template_id=payload.dlt_template_id,
        dlt_sender_id=payload.dlt_sender_id,
        subject=payload.subject,
        body=payload.body,
        variables=payload.variables,
        is_active=payload.is_active,
    )
    db.add(tmpl)
    await db.commit()
    await db.refresh(tmpl)
    return tmpl


@router.put("/templates/{template_id}", response_model=NotificationTemplateResponse)
async def update_template(
    template_id: str,
    payload: NotificationTemplateUpdate,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(NotificationTemplate).where(NotificationTemplate.id == template_id)
    res = await db.execute(stmt)
    tmpl = res.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(tmpl, k, v)

    await db.commit()
    await db.refresh(tmpl)
    return tmpl


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(NotificationTemplate).where(NotificationTemplate.id == template_id)
    res = await db.execute(stmt)
    tmpl = res.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")

    await db.delete(tmpl)
    await db.commit()
    return {"success": True, "message": "Template deleted"}


# ============================================================
# Delivery Logs & Stats
# ============================================================
@router.get("/logs", response_model=List[NotificationLogResponse])
async def list_notification_logs(
    channel: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(NotificationLog)
    if channel:
        stmt = stmt.where(NotificationLog.channel == channel)
    if status:
        stmt = stmt.where(NotificationLog.status == status)
    if search:
        s = f"%{search}%"
        stmt = stmt.where(or_(
            NotificationLog.recipient_phone.like(s),
            NotificationLog.content.like(s),
            NotificationLog.template_name.like(s),
        ))

    stmt = stmt.order_by(desc(NotificationLog.created_at)).limit(limit).offset(offset)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("/stats", response_model=NotificationStatsResponse)
async def get_notification_stats(db: AsyncSession = Depends(get_db)):
    tot_stmt = select(func.count(NotificationLog.id))
    tot_res = await db.execute(tot_stmt)
    total_dispatched = tot_res.scalar() or 0

    deliv_stmt = select(func.count(NotificationLog.id)).where(NotificationLog.status == "delivered")
    deliv_res = await db.execute(deliv_stmt)
    total_delivered = deliv_res.scalar() or 0

    fail_stmt = select(func.count(NotificationLog.id)).where(NotificationLog.status == "failed")
    fail_res = await db.execute(fail_stmt)
    total_failed = fail_res.scalar() or 0

    opt_stmt = select(func.count(NotificationLog.id)).where(NotificationLog.status == "opted_out")
    opt_res = await db.execute(opt_stmt)
    total_opted_out = opt_res.scalar() or 0

    clk_stmt = select(func.sum(NotificationLog.click_count))
    clk_res = await db.execute(clk_stmt)
    total_clicks = clk_res.scalar() or 0

    # by channel
    chan_stmt = select(NotificationLog.channel, func.count(NotificationLog.id)).group_by(NotificationLog.channel)
    chan_res = await db.execute(chan_stmt)
    by_channel = {row[0]: row[1] for row in chan_res.fetchall()}

    delivery_rate = round((total_delivered / total_dispatched * 100), 1) if total_dispatched > 0 else 100.0
    ctr = round((total_clicks / total_delivered * 100), 1) if total_delivered > 0 else 0.0

    return {
        "total_dispatched": total_dispatched,
        "total_delivered": total_delivered,
        "total_failed": total_failed,
        "total_opted_out": total_opted_out,
        "total_clicks": total_clicks,
        "delivery_rate_percent": delivery_rate,
        "click_through_rate_percent": ctr,
        "by_channel": by_channel,
    }


# ============================================================
# Opt-Out Registry
# ============================================================
@router.get("/opt-outs", response_model=List[NotificationOptOutResponse])
async def list_opt_outs(
    phone: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(NotificationOptOut)
    if phone:
        stmt = stmt.where(NotificationOptOut.phone.like(f"%{phone}%"))
    stmt = stmt.order_by(desc(NotificationOptOut.opted_out_at))
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/opt-outs", response_model=NotificationOptOutResponse)
async def register_opt_out(
    payload: NotificationOptOutCreate,
    db: AsyncSession = Depends(get_db),
):
    opt = NotificationOptOut(
        phone=payload.phone.strip(),
        email=payload.email,
        channel=payload.channel,
        reason=payload.reason,
        source=payload.source,
        opted_out_at=utc_now(),
    )
    db.add(opt)
    await db.commit()
    await db.refresh(opt)
    return opt


@router.delete("/opt-outs/{opt_out_id}")
async def delete_opt_out(
    opt_out_id: str,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(NotificationOptOut).where(NotificationOptOut.id == opt_out_id)
    res = await db.execute(stmt)
    opt = res.scalar_one_or_none()
    if not opt:
        raise HTTPException(status_code=404, detail="Opt-out record not found")
    await db.delete(opt)
    await db.commit()
    return {"success": True, "message": "Opt-out removed"}


# ============================================================
# Manual Dispatch
# ============================================================
@router.post("/send-manual", response_model=NotificationLogResponse)
async def send_manual_notification(
    payload: SendManualNotificationRequest,
    db: AsyncSession = Depends(get_db),
):
    log = await NotificationService.dispatch(
        db,
        channel=payload.channel,
        recipient_phone=payload.recipient_phone,
        recipient_email=payload.recipient_email,
        template_name=payload.template_name,
        custom_content=payload.custom_content,
        variables=payload.variables,
        category=payload.category,
        ticket_id=payload.ticket_id,
        client_id=payload.client_id,
    )
    return log
