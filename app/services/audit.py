from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit import AuditLog
from app.models.user import User


class AuditService:
    @staticmethod
    async def log_event(
        db: AsyncSession,
        action: str,
        entity: str,
        entity_id: Optional[str] = None,
        actor: Optional[User] = None,
        branch_id: Optional[str] = None,
        before_state: Optional[Dict[str, Any]] = None,
        after_state: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLog:
        """
        Creates an immutable append-only audit trail record.
        """
        actor_id = actor.id if actor else None
        actor_name = actor.full_name if actor else "System"
        actor_email = actor.email if actor else None
        actor_role = actor.role.name if actor and actor.role else None
        effective_branch_id = branch_id or (actor.branch_id if actor else None)

        audit_entry = AuditLog(
            actor_id=actor_id,
            actor_name=actor_name,
            actor_email=actor_email,
            actor_role=actor_role,
            branch_id=effective_branch_id,
            action=action.upper(),
            entity=entity,
            entity_id=str(entity_id) if entity_id else None,
            before_state=before_state,
            after_state=after_state,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        db.add(audit_entry)
        await db.commit()
        await db.refresh(audit_entry)
        return audit_entry


async def log_audit_event(
    db: AsyncSession,
    action: str,
    entity: str,
    entity_id: Optional[str] = None,
    actor: Optional[User] = None,
    actor_id: Optional[str] = None,
    module: Optional[str] = None,
    branch_id: Optional[str] = None,
    before_state: Optional[Dict[str, Any]] = None,
    after_state: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditLog:
    return await AuditService.log_event(
        db=db,
        action=action,
        entity=entity,
        entity_id=entity_id,
        actor=actor,
        branch_id=branch_id,
        before_state=before_state,
        after_state=after_state,
        ip_address=ip_address,
        user_agent=user_agent,
    )
