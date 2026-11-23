from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.deps import get_db, require_permission
from app.models.user import User
from app.models.handbook import Handbook, HandbookItem
from app.schemas.handbook import (
    HandbookCreate,
    HandbookUpdate,
    HandbookResponse,
    HandbookDetailResponse,
    HandbookItemCreate,
    HandbookItemUpdate,
    HandbookItemResponse,
)
from app.models.base import generate_uuid

router = APIRouter(prefix="/settings/handbooks", tags=["Settings - Handbooks"])


@router.get("", response_model=List[HandbookDetailResponse])
async def list_handbooks(
    branch_id: Optional[str] = Query(None, description="Filter by branch ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "VIEW_ONLY")),
):
    stmt = (
        select(Handbook)
        .options(selectinload(Handbook.items))
        .order_by(Handbook.created_at.asc())
    )
    if branch_id is not None:
        stmt = stmt.where((Handbook.branch_id == branch_id) | (Handbook.branch_id == None))

    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=HandbookDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_handbook(
    payload: HandbookCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    hb = Handbook(
        id=generate_uuid(),
        branch_id=payload.branch_id,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        is_hierarchical=payload.is_hierarchical,
        is_system=payload.is_system,
        is_active=payload.is_active,
    )
    db.add(hb)
    await db.commit()

    stmt = select(Handbook).options(selectinload(Handbook.items)).where(Handbook.id == hb.id)
    return (await db.execute(stmt)).scalar_one()


@router.get("/{id}", response_model=HandbookDetailResponse)
async def get_handbook(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "VIEW_ONLY")),
):
    stmt = select(Handbook).options(selectinload(Handbook.items)).where(Handbook.id == id)
    hb = (await db.execute(stmt)).scalar_one_or_none()
    if not hb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Handbook not found")
    return hb


@router.put("/{id}", response_model=HandbookResponse)
async def update_handbook(
    id: str,
    payload: HandbookUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    stmt = select(Handbook).where(Handbook.id == id)
    hb = (await db.execute(stmt)).scalar_one_or_none()
    if not hb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Handbook not found")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(hb, k, v)

    await db.commit()
    await db.refresh(hb)
    return hb


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_handbook(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    stmt = select(Handbook).where(Handbook.id == id)
    hb = (await db.execute(stmt)).scalar_one_or_none()
    if not hb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Handbook not found")

    await db.delete(hb)
    await db.commit()


# Handbook Items
@router.post("/{handbook_id}/items", response_model=HandbookItemResponse, status_code=status.HTTP_201_CREATED)
async def create_handbook_item(
    handbook_id: str,
    payload: HandbookItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    item = HandbookItem(
        id=generate_uuid(),
        handbook_id=handbook_id,
        parent_id=payload.parent_id,
        code=payload.code,
        name=payload.name,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
        extra_data=payload.extra_data,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.put("/items/{item_id}", response_model=HandbookItemResponse)
async def update_handbook_item(
    item_id: str,
    payload: HandbookItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    stmt = select(HandbookItem).where(HandbookItem.id == item_id)
    item = (await db.execute(stmt)).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Handbook item not found")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(item, k, v)

    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_handbook_item(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    stmt = select(HandbookItem).where(HandbookItem.id == item_id)
    item = (await db.execute(stmt)).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Handbook item not found")

    await db.delete(item)
    await db.commit()
