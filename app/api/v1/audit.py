from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.deps import get_branch_scope, BranchScope, require_permission
from app.db.session import get_db
from app.models.audit import AuditLog
from pydantic import BaseModel
from datetime import datetime

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


class AuditLogItem(BaseModel):
    id: str
    actor_id: Optional[str]
    actor_name: Optional[str]
    actor_email: Optional[str]
    actor_role: Optional[str]
    branch_id: Optional[str]
    action: str
    entity: str
    entity_id: Optional[str]
    before_state: Optional[dict]
    after_state: Optional[dict]
    ip_address: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogPage(BaseModel):
    items: List[AuditLogItem]
    total: int
    page: int
    limit: int
    total_pages: int


@router.get("", response_model=AuditLogPage)
async def get_audit_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    entity: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    branch_scope: BranchScope = Depends(get_branch_scope),
    _=Depends(require_permission("settings", "VIEW_ONLY")),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * limit
    stmt = select(AuditLog)

    # Scoped by branch unless owner and viewing all
    if branch_scope.branch_id:
        stmt = stmt.where(AuditLog.branch_id == branch_scope.branch_id)

    if entity:
        stmt = stmt.where(AuditLog.entity == entity)

    if action:
        stmt = stmt.where(AuditLog.action == action.upper())

    if search:
        search_term = f"%{search}%"
        stmt = stmt.where(
            (AuditLog.actor_name.ilike(search_term))
            | (AuditLog.actor_email.ilike(search_term))
            | (AuditLog.entity_id.ilike(search_term))
        )

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    # Paginated results ordered by newest first
    stmt = stmt.order_by(desc(AuditLog.created_at)).offset(offset).limit(limit)
    res = await db.execute(stmt)
    records = res.scalars().all()

    total_pages = (total + limit - 1) // limit if total > 0 else 1

    return AuditLogPage(
        items=records,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )
