from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, desc
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.notice_board import NoticeBoardPost, NoticeResponse
from app.models.user import User
from app.models.branch import Branch
from app.core.deps import get_current_user
from app.schemas.notice_board import (
    NoticeBoardPostCreate,
    NoticeBoardPostUpdate,
    NoticeBoardPostResponse,
    NoticeResponseCreate,
    NoticeResponseItem,
)

router = APIRouter(prefix="/notices", tags=["Ads & Notice Board"])


@router.get("", response_model=List[NoticeBoardPostResponse])
async def list_notices(
    category: Optional[str] = Query(None, description="Filter by category"),
    urgency: Optional[str] = Query(None, description="Filter by urgency tier"),
    status_filter: Optional[str] = Query("open", alias="status", description="open, in_progress, closed, all"),
    branch_id: Optional[str] = Query(None, description="Filter by branch (null = include enterprise global)"),
    q: Optional[str] = Query(None, description="Search keyword in title or description"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    List bulletin posts across subcontracting, spare sourcing, and internal notices.
    """
    stmt = (
        select(NoticeBoardPost)
        .options(
            selectinload(NoticeBoardPost.author).selectinload(User.role),
            selectinload(NoticeBoardPost.branch),
            selectinload(NoticeBoardPost.responses).selectinload(NoticeResponse.responder).selectinload(User.role),
        )
        .order_by(
            # Critical urgency first, then newest
            desc(NoticeBoardPost.urgency == "critical"),
            desc(NoticeBoardPost.urgency == "high"),
            desc(NoticeBoardPost.created_at),
        )
        .limit(limit)
        .offset(offset)
    )

    if category and category != "all":
        stmt = stmt.where(NoticeBoardPost.category == category)

    if urgency and urgency != "all":
        stmt = stmt.where(NoticeBoardPost.urgency == urgency)

    if status_filter and status_filter != "all":
        stmt = stmt.where(NoticeBoardPost.status == status_filter)

    if branch_id:
        stmt = stmt.where(or_(NoticeBoardPost.branch_id == branch_id, NoticeBoardPost.branch_id == None))

    if q:
        like_term = f"%{q}%"
        stmt = stmt.where(
            or_(
                NoticeBoardPost.title.ilike(like_term),
                NoticeBoardPost.description.ilike(like_term),
                NoticeBoardPost.part_number_or_sku.ilike(like_term),
                NoticeBoardPost.device_model.ilike(like_term),
            )
        )

    result = await db.execute(stmt)
    posts = result.scalars().all()

    response_items = []
    for p in posts:
        resp_models = []
        for r in p.responses:
            resp_models.append(
                NoticeResponseItem(
                    id=r.id,
                    post_id=r.post_id,
                    responder_id=r.responder_id,
                    responder_name=r.responder.full_name or r.responder.email if r.responder else "User",
                    responder_role=r.responder.role.name if r.responder and r.responder.role else "Technician",
                    quote_amount=r.quote_amount,
                    message=r.message,
                    estimated_delivery_days=r.estimated_delivery_days,
                    status=r.status,
                    created_at=r.created_at,
                )
            )

        response_items.append(
            NoticeBoardPostResponse(
                id=p.id,
                author_id=p.author_id,
                author_name=p.author.full_name or p.author.email if p.author else "OmniSuite Staff",
                author_role=p.author.role.name if p.author and p.author.role else "Staff",
                branch_name=p.branch.name if p.branch else "Enterprise (All Branches)",
                category=p.category,
                title=p.title,
                description=p.description,
                urgency=p.urgency,
                status=p.status,
                budget_or_price=p.budget_or_price,
                currency=p.currency,
                part_number_or_sku=p.part_number_or_sku,
                device_model=p.device_model,
                contact_phone=p.contact_phone,
                contact_email=p.contact_email,
                location_city=p.location_city,
                branch_id=p.branch_id,
                expires_at=p.expires_at,
                attachments=p.attachments or [],
                responses_count=len(resp_models),
                responses=resp_models,
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
        )

    return response_items


@router.post("", response_model=NoticeBoardPostResponse, status_code=status.HTTP_201_CREATED)
async def create_notice(
    payload: NoticeBoardPostCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Publish a new tender, spare sourcing, subcontracting bulletin, or internal announcement.
    """
    post = NoticeBoardPost(
        branch_id=payload.branch_id or current_user.branch_id,
        author_id=current_user.id,
        category=payload.category,
        title=payload.title,
        description=payload.description,
        urgency=payload.urgency,
        budget_or_price=payload.budget_or_price,
        currency=payload.currency,
        part_number_or_sku=payload.part_number_or_sku,
        device_model=payload.device_model,
        contact_phone=payload.contact_phone or getattr(current_user, "phone", None),
        contact_email=payload.contact_email or current_user.email,
        location_city=payload.location_city,
        expires_at=payload.expires_at,
        attachments=payload.attachments or [],
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)

    # Re-query with eager relationships
    stmt = (
        select(NoticeBoardPost)
        .options(
            selectinload(NoticeBoardPost.author).selectinload(User.role),
            selectinload(NoticeBoardPost.branch),
            selectinload(NoticeBoardPost.responses),
        )
        .where(NoticeBoardPost.id == post.id)
    )
    res = await db.execute(stmt)
    full_post = res.scalar_one()

    return NoticeBoardPostResponse(
        id=full_post.id,
        author_id=full_post.author_id,
        author_name=full_post.author.full_name or full_post.author.email if full_post.author else "Staff",
        author_role=full_post.author.role.name if full_post.author and full_post.author.role else "Staff",
        branch_name=full_post.branch.name if full_post.branch else "Enterprise (All Branches)",
        category=full_post.category,
        title=full_post.title,
        description=full_post.description,
        urgency=full_post.urgency,
        status=full_post.status,
        budget_or_price=full_post.budget_or_price,
        currency=full_post.currency,
        part_number_or_sku=full_post.part_number_or_sku,
        device_model=full_post.device_model,
        contact_phone=full_post.contact_phone,
        contact_email=full_post.contact_email,
        location_city=full_post.location_city,
        branch_id=full_post.branch_id,
        expires_at=full_post.expires_at,
        attachments=full_post.attachments or [],
        responses_count=0,
        responses=[],
        created_at=full_post.created_at,
        updated_at=full_post.updated_at,
    )


@router.get("/{post_id}", response_model=NoticeBoardPostResponse)
async def get_notice(
    post_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get full details and submitted responses/quotes for a specific notice.
    """
    stmt = (
        select(NoticeBoardPost)
        .options(
            selectinload(NoticeBoardPost.author).selectinload(User.role),
            selectinload(NoticeBoardPost.branch),
            selectinload(NoticeBoardPost.responses).selectinload(NoticeResponse.responder).selectinload(User.role),
        )
        .where(NoticeBoardPost.id == post_id)
    )
    res = await db.execute(stmt)
    post = res.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Bulletin post not found")

    resp_models = [
        NoticeResponseItem(
            id=r.id,
            post_id=r.post_id,
            responder_id=r.responder_id,
            responder_name=r.responder.full_name or r.responder.email if r.responder else "User",
            responder_role=r.responder.role.name if r.responder and r.responder.role else "Technician",
            quote_amount=r.quote_amount,
            message=r.message,
            estimated_delivery_days=r.estimated_delivery_days,
            status=r.status,
            created_at=r.created_at,
        )
        for r in post.responses
    ]

    return NoticeBoardPostResponse(
        id=post.id,
        author_id=post.author_id,
        author_name=post.author.full_name or post.author.email if post.author else "Staff",
        author_role=post.author.role.name if post.author and post.author.role else "Staff",
        branch_name=post.branch.name if post.branch else "Enterprise (All Branches)",
        category=post.category,
        title=post.title,
        description=post.description,
        urgency=post.urgency,
        status=post.status,
        budget_or_price=post.budget_or_price,
        currency=post.currency,
        part_number_or_sku=post.part_number_or_sku,
        device_model=post.device_model,
        contact_phone=post.contact_phone,
        contact_email=post.contact_email,
        location_city=post.location_city,
        branch_id=post.branch_id,
        expires_at=post.expires_at,
        attachments=post.attachments or [],
        responses_count=len(resp_models),
        responses=resp_models,
        created_at=post.created_at,
        updated_at=post.updated_at,
    )


@router.put("/{post_id}", response_model=NoticeBoardPostResponse)
async def update_notice(
    post_id: str,
    payload: NoticeBoardPostUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update post status or information.
    """
    stmt = select(NoticeBoardPost).where(NoticeBoardPost.id == post_id)
    res = await db.execute(stmt)
    post = res.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Bulletin post not found")

    for field, val in payload.model_dump(exclude_unset=True).items():
        setattr(post, field, val)

    await db.commit()
    return await get_notice(post_id, db)


@router.delete("/{post_id}")
async def delete_notice(
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Close or remove a bulletin post.
    """
    stmt = select(NoticeBoardPost).where(NoticeBoardPost.id == post_id)
    res = await db.execute(stmt)
    post = res.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Bulletin post not found")

    await db.delete(post)
    await db.commit()
    return {"success": True, "message": "Notice board post removed"}


@router.post("/{post_id}/responses", response_model=NoticeResponseItem, status_code=status.HTTP_201_CREATED)
async def submit_notice_response(
    post_id: str,
    payload: NoticeResponseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a quotation or response to an active tender or spare sourcing post.
    """
    stmt = select(NoticeBoardPost).where(NoticeBoardPost.id == post_id)
    res = await db.execute(stmt)
    post = res.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Bulletin post not found")

    resp = NoticeResponse(
        post_id=post.id,
        responder_id=current_user.id,
        quote_amount=payload.quote_amount,
        message=payload.message,
        estimated_delivery_days=payload.estimated_delivery_days,
        status="pending",
    )
    db.add(resp)
    post.responses_count += 1
    await db.commit()
    await db.refresh(resp)

    return NoticeResponseItem(
        id=resp.id,
        post_id=resp.post_id,
        responder_id=resp.responder_id,
        responder_name=current_user.full_name or current_user.email,
        responder_role=current_user.role.name if current_user.role else "Technician",
        quote_amount=resp.quote_amount,
        message=resp.message,
        estimated_delivery_days=resp.estimated_delivery_days,
        status=resp.status,
        created_at=resp.created_at,
    )
