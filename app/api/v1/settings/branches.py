from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.deps import get_db, require_permission
from app.models.user import User
from app.models.branch import Branch
from app.schemas.branch import (
    BranchCreate,
    BranchUpdate,
    BranchResponse,
)
from app.models.base import generate_uuid
from app.services.audit import log_audit_event

router = APIRouter(prefix="/settings/branches", tags=["Settings - Branches"])


@router.get("", response_model=List[BranchResponse])
async def list_branches(
    is_active: Optional[bool] = Query(None, description="Filter active status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "VIEW_ONLY")),
):
    stmt = select(Branch).order_by(Branch.name.asc())
    if is_active is not None:
        stmt = stmt.where(Branch.is_active == is_active)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=BranchResponse, status_code=status.HTTP_201_CREATED)
async def create_branch(
    payload: BranchCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "FULL")),
):
    # Verify code uniqueness
    check = await db.execute(select(Branch).where(Branch.code == payload.code.upper()))
    if check.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Branch code '{payload.code.upper()}' is already in use",
        )

    branch = Branch(
        id=generate_uuid(),
        name=payload.name,
        code=payload.code.upper(),
        phone=payload.phone,
        email=payload.email,
        address_line=payload.address_line,
        city=payload.city,
        state=payload.state,
        state_code=payload.state_code,
        pincode=payload.pincode,
        gstin=payload.gstin,
        currency=payload.currency.upper(),
        is_active=payload.is_active,
        settings=payload.settings,
    )
    db.add(branch)
    await db.commit()
    await db.refresh(branch)

    await log_audit_event(
        db=db,
        action="BRANCH_CREATE",
        module="settings",
        entity="branches",
        entity_id=branch.id,
        actor_id=current_user.id,
        after_state={"name": branch.name, "code": branch.code, "gstin": branch.gstin},
    )

    return branch


@router.get("/{id}", response_model=BranchResponse)
async def get_branch(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "VIEW_ONLY")),
):
    stmt = select(Branch).where(Branch.id == id)
    branch = (await db.execute(stmt)).scalar_one_or_none()
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
    return branch


@router.put("/{id}", response_model=BranchResponse)
async def update_branch(
    id: str,
    payload: BranchUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "FULL")),
):
    stmt = select(Branch).where(Branch.id == id)
    branch = (await db.execute(stmt)).scalar_one_or_none()
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "currency" in update_data and update_data["currency"]:
        update_data["currency"] = update_data["currency"].upper()

    for k, v in update_data.items():
        setattr(branch, k, v)

    await db.commit()
    await db.refresh(branch)

    await log_audit_event(
        db=db,
        action="BRANCH_UPDATE",
        module="settings",
        entity="branches",
        entity_id=branch.id,
        actor_id=current_user.id,
        after_state=update_data,
    )

    return branch


@router.delete("/{id}", response_model=BranchResponse)
async def toggle_branch_status(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "FULL")),
):
    stmt = select(Branch).where(Branch.id == id)
    branch = (await db.execute(stmt)).scalar_one_or_none()
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")

    branch.is_active = not branch.is_active
    await db.commit()
    await db.refresh(branch)

    await log_audit_event(
        db=db,
        action="BRANCH_STATUS_TOGGLE",
        module="settings",
        entity="branches",
        entity_id=branch.id,
        actor_id=current_user.id,
        after_state={"is_active": branch.is_active},
    )

    return branch
