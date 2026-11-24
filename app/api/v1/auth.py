from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.models.branch import Branch
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshTokenRequest, TokenResponse
from app.schemas.user import BranchRead, UserRead
from app.services.audit import AuditService

router = APIRouter(prefix="/auth", tags=["Authentication"])


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, description="Minimum 8 characters")


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    db_url = getattr(getattr(db, "bind", None), "url", "unknown")
    print(f"🔑 [AUTH DEBUG] Login attempt: email='{body.email}', DB='{db_url}'")

    stmt = (
        select(User)
        .options(
            selectinload(User.branch),
        )
        .where(User.email == body.email.strip().lower())
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        print(f"❌ [AUTH DEBUG] No user found with email '{body.email}' in {db_url}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"No account found with email '{body.email}'",
        )

    pw_valid = verify_password(body.password, user.hashed_password)
    print(f"🔑 [AUTH DEBUG] Password validation for '{user.email}': {pw_valid}")

    if not pw_valid:
        print(f"❌ [AUTH DEBUG] Password mismatch for '{user.email}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password for this account",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is deactivated. Please contact your administrator.",
        )

    # Update last login timestamp
    user.last_login = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)

    role_slug = user.role_slug if hasattr(user, "role_slug") else "super_admin"
    if isinstance(user.role, dict):
        role_slug = user.role.get("slug", role_slug)
    elif hasattr(user.role, "slug"):
        role_slug = user.role.slug

    # Generate tokens (Super admin does not require a branch)
    access_token = create_access_token(
        subject=user.id,
        claims={
            "email": user.email,
            "role": role_slug,
            "branch_id": user.branch_id,
        },
    )
    refresh_token = create_refresh_token(subject=user.id)

    # Log audit event
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    await AuditService.log_event(
        db=db,
        action="LOGIN",
        entity="User",
        entity_id=user.id,
        actor=user,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user=user,
    )


@router.post("/refresh")
async def refresh_token_endpoint(
    body: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = payload.get("sub")
    stmt = (
        select(User)
        .options(
            selectinload(User.branch),
        )
        .where(User.id == user_id)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    role_slug = user.role_slug if hasattr(user, "role_slug") else "super_admin"
    if isinstance(user.role, dict):
        role_slug = user.role.get("slug", role_slug)
    elif hasattr(user.role, "slug"):
        role_slug = user.role.slug

    new_access_token = create_access_token(
        subject=user.id,
        claims={
            "email": user.email,
            "role": role_slug,
            "branch_id": user.branch_id,
        },
    )

    return {
        "access_token": new_access_token,
        "token_type": "bearer",
    }


@router.post("/change-password")
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password verification failed",
        )

    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password",
        )

    current_user.hashed_password = get_password_hash(body.new_password)
    current_user.must_change_password = False
    await db.commit()
    await db.refresh(current_user)

    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    await AuditService.log_event(
        db=db,
        action="PASSWORD_CHANGE",
        entity="User",
        entity_id=current_user.id,
        actor=current_user,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    return {"message": "Password updated successfully"}


@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/logout")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    await AuditService.log_event(
        db=db,
        action="LOGOUT",
        entity="User",
        entity_id=current_user.id,
        actor=current_user,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    return {"message": "Successfully logged out"}


@router.get("/branches", response_model=List[BranchRead])
async def list_branches_for_user(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns branches accessible to user:
    - Super admins (Owner) see all active branches.
    - Other staff see only their assigned branch.
    """
    is_super = current_user.is_superuser or (
        current_user.role_slug in ("super_admin", "owner")
    )

    stmt = select(Branch).where(Branch.is_active == True)
    if not is_super:
        stmt = stmt.where(Branch.id == current_user.branch_id)

    result = await db.execute(stmt)
    return result.scalars().all()
