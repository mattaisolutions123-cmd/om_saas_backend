from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.db.session import get_db
from app.models.automation import MarketingCampaign
from app.schemas.automation import (
    MarketingCampaignCreate,
    MarketingCampaignUpdate,
    MarketingCampaignResponse,
    SegmentPreviewRequest,
    SegmentPreviewResponse,
)
from app.services.automation_service import AutomationService

router = APIRouter(prefix="/campaigns", tags=["Marketing Campaigns & Audience Segments"])


@router.get("", response_model=List[MarketingCampaignResponse])
async def list_campaigns(
    branch_id: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(MarketingCampaign)
    if branch_id:
        stmt = stmt.where(MarketingCampaign.branch_id == branch_id)
    if status:
        stmt = stmt.where(MarketingCampaign.status == status)

    stmt = stmt.order_by(desc(MarketingCampaign.created_at))
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("", response_model=MarketingCampaignResponse)
async def create_campaign(
    payload: MarketingCampaignCreate,
    db: AsyncSession = Depends(get_db),
):
    camp = MarketingCampaign(
        branch_id=payload.branch_id,
        name=payload.name,
        channel=payload.channel,
        segment_type=payload.segment_type,
        segment_criteria=payload.segment_criteria,
        template_id=payload.template_id,
        custom_message=payload.custom_message,
        scheduled_at=payload.scheduled_at,
        status="draft",
    )
    db.add(camp)
    await db.commit()
    await db.refresh(camp)
    return camp


@router.get("/{campaign_id}", response_model=MarketingCampaignResponse)
async def get_campaign(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(MarketingCampaign).where(MarketingCampaign.id == campaign_id)
    res = await db.execute(stmt)
    camp = res.scalar_one_or_none()
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return camp


@router.post("/segments/preview", response_model=SegmentPreviewResponse)
async def preview_segment(
    payload: SegmentPreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Evaluates audience size and scrubs against TRAI DLT Opt-Out Registry
    to give a precise count of eligible vs opted-out recipients.
    """
    return await AutomationService.evaluate_segment(
        db,
        segment_type=payload.segment_type,
        segment_criteria=payload.segment_criteria,
        branch_id=payload.branch_id,
    )


@router.post("/{campaign_id}/send")
async def send_campaign(
    campaign_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Broadcasts campaign to segment with automatic opt-out scrubbing.
    """
    base_url = str(request.base_url).rstrip("/")
    return await AutomationService.broadcast_campaign(db, campaign_id, base_url=base_url)
