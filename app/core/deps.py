from typing import AsyncGenerator, Callable, Dict, Optional, Set
from fastapi import Depends, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import decode_token
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.models.rbac import Role, RolePermission

# Optional auth scheme so we can handle 401s cleanly
security_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch user with role and permissions loaded
    stmt = (
        select(User)
        .options(
            selectinload(User.role).selectinload(Role.permissions),
            selectinload(User.branch),
        )
        .where(User.id == user_id)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )

    return user


# Access hierarchy weight mapping for fine-grained check
ACCESS_LEVEL_WEIGHTS: Dict[str, int] = {
    "NONE": 0,
    "VIEW ONLY": 1,
    "VIEW_ONLY": 1,
    "OWN COMMISSION": 2,
    "OWN_COMMISSION": 2,
    "ASSIGNED ONLY": 3,
    "ASSIGNED_ONLY": 3,
    "ASSIGNED JOBS": 3,
    "ASSIGNED_JOBS": 3,
    "CONSUME ONLY": 3,
    "CONSUME_ONLY": 3,
    "DESK TASKS": 4,
    "DESK_TASKS": 4,
    "INTAKE/DELIVER": 4,
    "INTAKE_DELIVER": 4,
    "STOCK VIEW": 4,
    "STOCK_VIEW": 4,
    "LOOKUP/CREATE": 4,
    "LOOKUP_CREATE": 4,
    "POST/VIEW": 4,
    "POST_VIEW": 4,
    "ACTIVE REGISTER": 5,
    "ACTIVE_REGISTER": 5,
    "DAILY REGISTER": 5,
    "DAILY_REGISTER": 5,
    "FULL POS": 6,
    "FULL_POS": 6,
    "BRANCH STOCK": 7,
    "BRANCH_STOCK": 7,
    "BRANCH CASH": 7,
    "BRANCH_CASH": 7,
    "BRANCH REP": 7,
    "BRANCH_REP": 7,
    "RESTRICTED": 7,
    "BRANCH": 8,
    "FULL": 10,
}


def require_permission(module: str, min_level: str = "VIEW_ONLY") -> Callable:
    """
    Enforces RBAC on backend endpoints.
    Owner / Superusers always have FULL access to all modules.
    For other roles, checks role_permissions table.
    """
    normalized_module = module.strip().lower()
    min_weight = ACCESS_LEVEL_WEIGHTS.get(min_level.upper(), 1)

    async def permission_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        # Superuser and Owner role have unrestricted FULL access
        if current_user.is_superuser or (current_user.role and current_user.role.slug == "owner"):
            return current_user

        if not current_user.role or not current_user.role.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: No permissions assigned for role '{current_user.role.name if current_user.role else 'None'}'",
            )

        # Find matching module permission
        user_perm = None
        for p in current_user.role.permissions:
            if p.module.strip().lower() == normalized_module:
                user_perm = p
                break

        if not user_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: No permission configured for module '{module}'",
            )

        perm_level = user_perm.access_level.strip().upper()
        if perm_level == "NONE":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Module '{module}' is disabled for your role",
            )

        user_weight = ACCESS_LEVEL_WEIGHTS.get(perm_level, 1)
        if user_weight < min_weight:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Required '{min_level}' on module '{module}', but role has '{perm_level}'",
            )

        return current_user

    return permission_checker


class BranchScope:
    """
    Encapsulates row-level branch scoping:
    - Owners / Super Admins can see all branches or narrow by header/query.
    - Branch Managers, Cashiers, Technicians are strictly locked to their assigned branch.
    """
    def __init__(
        self,
        branch_id: Optional[str],
        is_owner: bool,
        user: User,
    ):
        self.branch_id = branch_id
        self.is_owner = is_owner
        self.user = user

    def apply_filter(self, query, model_branch_col):
        """Applies SQL filter to a SQLAlchemy query if scoped to a branch."""
        if self.branch_id:
            return query.where(model_branch_col == self.branch_id)
        return query


async def get_branch_scope(
    current_user: User = Depends(get_current_user),
    x_branch_id: Optional[str] = Header(None, alias="X-Branch-Id"),
    query_branch_id: Optional[str] = Query(None, alias="branch_id"),
) -> BranchScope:
    is_owner = current_user.is_superuser or (
        current_user.role and current_user.role.slug == "owner"
    )

    if is_owner:
        # Owner can optionally filter to a specific branch via header or query param
        target_branch_id = x_branch_id or query_branch_id
        return BranchScope(branch_id=target_branch_id, is_owner=True, user=current_user)
    else:
        # Strict enforcement: non-owners are always scoped to their assigned branch
        if not current_user.branch_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is not assigned to any branch",
            )
        return BranchScope(branch_id=current_user.branch_id, is_owner=False, user=current_user)
