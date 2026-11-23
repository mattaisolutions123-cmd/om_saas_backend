from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.deps import get_db, require_permission
from app.core.security import get_password_hash
from app.models.user import User
from app.models.rbac import Role, RolePermission
from app.models.branch import Branch
from app.schemas.staff_role import (
    StaffInviteRequest,
    StaffUpdateRequest,
    StaffUserResponse,
    RoleItemResponse,
    RolePermissionUpdateRequest,
)
from app.models.base import generate_uuid
from app.services.audit import log_audit_event

router = APIRouter(prefix="/settings", tags=["Settings - Staff & Roles"])


@router.get("/staff", response_model=List[StaffUserResponse])
async def list_staff(
    branch_id: Optional[str] = Query(None, description="Filter by branch"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    stmt = (
        select(User)
        .options(
            selectinload(User.role),
            selectinload(User.branch),
        )
        .order_by(User.full_name.asc())
    )
    if branch_id is not None:
        stmt = stmt.where((User.branch_id == branch_id) | (User.branch_id == None))

    users = (await db.execute(stmt)).scalars().all()
    results = []
    for u in users:
        results.append(
            StaffUserResponse(
                id=u.id,
                email=u.email,
                full_name=u.full_name,
                phone=u.phone,
                role_id=u.role_id,
                role_name=u.role.name if u.role else None,
                role_slug=u.role.slug if u.role else None,
                branch_id=u.branch_id,
                branch_name=u.branch.name if u.branch else "All Branches (Cross-Branch)",
                is_active=u.is_active,
                created_at=u.created_at,
            )
        )
    return results


@router.post("/staff/invite", response_model=StaffUserResponse, status_code=status.HTTP_201_CREATED)
async def invite_staff(
    payload: StaffInviteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "FULL")),
):
    # Verify email uniqueness
    check = await db.execute(select(User).where(User.email == payload.email.lower()))
    if check.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is already registered")

    # Verify role exists
    role_check = await db.execute(select(Role).where(Role.id == payload.role_id))
    role = role_check.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected role does not exist")

    # Verify branch exists if supplied
    branch = None
    if payload.branch_id:
        b_check = await db.execute(select(Branch).where(Branch.id == payload.branch_id))
        branch = b_check.scalar_one_or_none()
        if not branch:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected branch does not exist")

    new_user = User(
        id=generate_uuid(),
        email=payload.email.lower(),
        hashed_password=get_password_hash(payload.initial_password or "Password@123"),
        full_name=payload.full_name,
        phone=payload.phone,
        role_id=payload.role_id,
        branch_id=payload.branch_id,
        is_active=True,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    await log_audit_event(
        db=db,
        action="STAFF_INVITE",
        module="settings",
        entity="users",
        entity_id=new_user.id,
        actor_id=current_user.id,
        after_state={"email": new_user.email, "role": role.slug, "branch_id": payload.branch_id},
    )

    return StaffUserResponse(
        id=new_user.id,
        email=new_user.email,
        full_name=new_user.full_name,
        phone=new_user.phone,
        role_id=new_user.role_id,
        role_name=role.name,
        role_slug=role.slug,
        branch_id=new_user.branch_id,
        branch_name=branch.name if branch else "All Branches (Cross-Branch)",
        is_active=new_user.is_active,
        created_at=new_user.created_at,
    )


@router.put("/staff/{user_id}", response_model=StaffUserResponse)
async def update_staff(
    user_id: str,
    payload: StaffUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "FULL")),
):
    stmt = (
        select(User)
        .options(
            selectinload(User.role),
            selectinload(User.branch),
        )
        .where(User.id == user_id)
    )
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff user not found")

    update_data = payload.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(user, k, v)

    await db.commit()
    await db.refresh(user)

    # Reload relations
    reloaded = (await db.execute(stmt)).scalar_one()

    await log_audit_event(
        db=db,
        action="STAFF_UPDATE",
        module="settings",
        entity="users",
        entity_id=user.id,
        actor_id=current_user.id,
        after_state=update_data,
    )

    return StaffUserResponse(
        id=reloaded.id,
        email=reloaded.email,
        full_name=reloaded.full_name,
        phone=reloaded.phone,
        role_id=reloaded.role_id,
        role_name=reloaded.role.name if reloaded.role else None,
        role_slug=reloaded.role.slug if reloaded.role else None,
        branch_id=reloaded.branch_id,
        branch_name=reloaded.branch.name if reloaded.branch else "All Branches (Cross-Branch)",
        is_active=reloaded.is_active,
        created_at=reloaded.created_at,
    )


# Role Permissions Matrix
@router.get("/roles", response_model=List[RoleItemResponse])
async def list_roles_with_permissions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "VIEW_ONLY")),
):
    stmt = (
        select(Role)
        .options(selectinload(Role.permissions))
        .order_by(Role.is_system.desc(), Role.name.asc())
    )
    roles = (await db.execute(stmt)).scalars().all()
    results = []
    for r in roles:
        perm_dict = {p.module: p.access_level for p in (r.permissions or [])}
        results.append(
            RoleItemResponse(
                id=r.id,
                name=r.name,
                slug=r.slug,
                description=r.description,
                is_system=r.is_system,
                permissions=perm_dict,
            )
        )
    return results


@router.put("/roles/matrix", status_code=status.HTTP_200_OK)
async def update_role_permissions(
    payload: RolePermissionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "FULL")),
):
    stmt = select(Role).options(selectinload(Role.permissions)).where(Role.id == payload.role_id)
    role = (await db.execute(stmt)).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    # Update or insert permissions for this role
    existing_perms = {p.module: p for p in role.permissions}
    for module_name, access_level in payload.permissions.items():
        if module_name in existing_perms:
            existing_perms[module_name].access_level = access_level.upper()
        else:
            new_perm = RolePermission(
                id=generate_uuid(),
                role_id=role.id,
                module=module_name,
                access_level=access_level.upper(),
            )
            db.add(new_perm)

    await db.commit()

    await log_audit_event(
        db=db,
        action="ROLE_PERMISSIONS_UPDATE",
        module="settings",
        entity="role_permissions",
        entity_id=role.id,
        actor_id=current_user.id,
        after_state={"role": role.slug, "permissions": payload.permissions},
    )

    return {"success": True, "role": role.slug, "permissions": payload.permissions}
