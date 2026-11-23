from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.deps import get_db, require_permission
from app.models.user import User
from app.models.pipeline import StatusPipeline, StatusDefinition, StatusTransition
from app.schemas.pipeline import (
    StatusPipelineCreate,
    StatusPipelineUpdate,
    StatusPipelineResponse,
    StatusPipelineDetailResponse,
    StatusDefinitionCreate,
    StatusDefinitionUpdate,
    StatusDefinitionResponse,
    StatusTransitionCreate,
    StatusTransitionUpdate,
    StatusTransitionResponse,
    TransitionValidateRequest,
    TransitionValidateResponse,
)
from app.models.base import generate_uuid
from app.services.audit import log_audit_event

router = APIRouter(prefix="/settings/pipelines", tags=["Settings - Pipelines"])


@router.get("", response_model=List[StatusPipelineDetailResponse])
async def list_pipelines(
    entity: Optional[str] = Query(None, description="Filter by entity (ticket, task)"),
    branch_id: Optional[str] = Query(None, description="Filter by branch"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "VIEW_ONLY")),
):
    stmt = (
        select(StatusPipeline)
        .options(
            selectinload(StatusPipeline.statuses),
            selectinload(StatusPipeline.transitions),
        )
        .order_by(StatusPipeline.created_at.asc())
    )
    if entity:
        stmt = stmt.where(StatusPipeline.entity == entity)
    if branch_id is not None:
        stmt = stmt.where((StatusPipeline.branch_id == branch_id) | (StatusPipeline.branch_id == None))

    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=StatusPipelineDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_pipeline(
    payload: StatusPipelineCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    pipe = StatusPipeline(
        id=generate_uuid(),
        branch_id=payload.branch_id,
        entity=payload.entity,
        name=payload.name,
        code=payload.code,
        description=payload.description,
        is_default=payload.is_default,
        is_active=payload.is_active,
    )
    db.add(pipe)
    await db.commit()
    await db.refresh(pipe)

    # Reload with empty statuses/transitions
    stmt = (
        select(StatusPipeline)
        .options(
            selectinload(StatusPipeline.statuses),
            selectinload(StatusPipeline.transitions),
        )
        .where(StatusPipeline.id == pipe.id)
    )
    return (await db.execute(stmt)).scalar_one()


@router.get("/{id}", response_model=StatusPipelineDetailResponse)
async def get_pipeline(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "VIEW_ONLY")),
):
    stmt = (
        select(StatusPipeline)
        .options(
            selectinload(StatusPipeline.statuses),
            selectinload(StatusPipeline.transitions),
        )
        .where(StatusPipeline.id == id)
    )
    pipe = (await db.execute(stmt)).scalar_one_or_none()
    if not pipe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")
    return pipe


@router.put("/{id}", response_model=StatusPipelineResponse)
async def update_pipeline(
    id: str,
    payload: StatusPipelineUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    stmt = select(StatusPipeline).where(StatusPipeline.id == id)
    pipe = (await db.execute(stmt)).scalar_one_or_none()
    if not pipe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    update_data = payload.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(pipe, k, v)

    await db.commit()
    await db.refresh(pipe)
    return pipe


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pipeline(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    stmt = select(StatusPipeline).where(StatusPipeline.id == id)
    pipe = (await db.execute(stmt)).scalar_one_or_none()
    if not pipe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    await db.delete(pipe)
    await db.commit()


# Status Nodes Endpoints
@router.post("/{pipeline_id}/statuses", response_model=StatusDefinitionResponse, status_code=status.HTTP_201_CREATED)
async def create_status(
    pipeline_id: str,
    payload: StatusDefinitionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    status_node = StatusDefinition(
        id=generate_uuid(),
        pipeline_id=pipeline_id,
        name=payload.name,
        code=payload.code,
        bg_color=payload.bg_color,
        text_color=payload.text_color,
        icon=payload.icon,
        sort_order=payload.sort_order,
        is_initial=payload.is_initial,
        is_terminal=payload.is_terminal,
        is_active=payload.is_active,
    )
    db.add(status_node)
    await db.commit()
    await db.refresh(status_node)
    return status_node


@router.put("/statuses/{status_id}", response_model=StatusDefinitionResponse)
async def update_status(
    status_id: str,
    payload: StatusDefinitionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    stmt = select(StatusDefinition).where(StatusDefinition.id == status_id)
    status_node = (await db.execute(stmt)).scalar_one_or_none()
    if not status_node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Status not found")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(status_node, k, v)

    await db.commit()
    await db.refresh(status_node)
    return status_node


@router.delete("/statuses/{status_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_status(
    status_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    stmt = select(StatusDefinition).where(StatusDefinition.id == status_id)
    status_node = (await db.execute(stmt)).scalar_one_or_none()
    if not status_node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Status not found")

    await db.delete(status_node)
    await db.commit()


# Transitions Endpoints
@router.post("/{pipeline_id}/transitions", response_model=StatusTransitionResponse, status_code=status.HTTP_201_CREATED)
async def create_transition(
    pipeline_id: str,
    payload: StatusTransitionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    trans = StatusTransition(
        id=generate_uuid(),
        pipeline_id=pipeline_id,
        from_status_id=payload.from_status_id,
        to_status_id=payload.to_status_id,
        name=payload.name,
        guards=payload.guards,
        event_hooks=payload.event_hooks,
        is_active=payload.is_active,
    )
    db.add(trans)
    await db.commit()
    await db.refresh(trans)
    return trans


@router.put("/transitions/{transition_id}", response_model=StatusTransitionResponse)
async def update_transition(
    transition_id: str,
    payload: StatusTransitionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    stmt = select(StatusTransition).where(StatusTransition.id == transition_id)
    trans = (await db.execute(stmt)).scalar_one_or_none()
    if not trans:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transition not found")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(trans, k, v)

    await db.commit()
    await db.refresh(trans)
    return trans


@router.delete("/transitions/{transition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transition(
    transition_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    stmt = select(StatusTransition).where(StatusTransition.id == transition_id)
    trans = (await db.execute(stmt)).scalar_one_or_none()
    if not trans:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transition not found")

    await db.delete(trans)
    await db.commit()


# Closure Gate & Guard Verification Evaluator
@router.post("/validate-transition", response_model=TransitionValidateResponse)
async def validate_transition(
    payload: TransitionValidateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "VIEW_ONLY")),
):
    stmt = select(StatusTransition).where(
        StatusTransition.pipeline_id == payload.pipeline_id,
        StatusTransition.from_status_id == payload.from_status_id,
        StatusTransition.to_status_id == payload.to_status_id,
        StatusTransition.is_active == True,
    )
    trans = (await db.execute(stmt)).scalar_one_or_none()

    if not trans:
        return TransitionValidateResponse(
            allowed=False,
            reasons=["Direct transition between these two status nodes is not permitted in this pipeline."],
        )

    guards = trans.guards or {}
    reasons: List[str] = []

    # 1. Closure Gate check (Closure gate: block 'Delivered' unless balance = 0 or manager override)
    if guards.get("closure_gate", False):
        if payload.current_balance > 0.00:
            if not payload.manager_override:
                reasons.append(
                    f"Closure Gate Blocked: Pending balance is ₹{payload.current_balance:.2f}. "
                    "Status cannot be moved to Delivered until balance is ₹0.00 or an authorized Manager Override is supplied."
                )
            else:
                # If manager override is claimed, ensure the actor is manager or owner
                if current_user.role and current_user.role.slug not in ["owner", "branch_manager"]:
                    reasons.append("Unauthorized Manager Override: Only a Branch Manager or Owner can override the closure gate.")

    # 2. Required custom fields check
    required_fields = guards.get("required_fields", [])
    for f_key in required_fields:
        val = payload.custom_field_values.get(f_key)
        if val is None or val == "":
            reasons.append(f"Guard requirement: Field '{f_key}' must be filled before moving to this status.")

    allowed = len(reasons) == 0
    return TransitionValidateResponse(
        allowed=allowed,
        transition_id=trans.id,
        reasons=reasons,
        event_hooks=trans.event_hooks if allowed else {},
    )
