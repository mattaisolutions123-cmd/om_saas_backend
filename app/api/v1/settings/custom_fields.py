from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.core.deps import get_db, require_permission
from app.models.user import User
from app.models.custom_field import CustomFieldDefinition
from app.schemas.custom_field import (
    CustomFieldCreate,
    CustomFieldUpdate,
    CustomFieldResponse,
)
from app.models.base import generate_uuid
from app.services.audit import log_audit_event

router = APIRouter(prefix="/settings/custom-fields", tags=["Settings - Custom Fields"])


@router.get("", response_model=List[CustomFieldResponse])
async def list_custom_fields(
    entity: Optional[str] = Query(None, description="Filter by entity: ticket, client, inventory, supplier, task"),
    branch_id: Optional[str] = Query(None, description="Filter by branch ID"),
    is_active: Optional[bool] = Query(None, description="Filter active status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "VIEW_ONLY")),
):
    stmt = select(CustomFieldDefinition).order_by(CustomFieldDefinition.sort_order.asc())

    if entity:
        stmt = stmt.where(CustomFieldDefinition.entity == entity)
    if is_active is not None:
        stmt = stmt.where(CustomFieldDefinition.is_active == is_active)
    if branch_id is not None:
        stmt = stmt.where(
            (CustomFieldDefinition.branch_id == branch_id) | (CustomFieldDefinition.branch_id == None)
        )

    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=CustomFieldResponse, status_code=status.HTTP_201_CREATED)
async def create_custom_field(
    payload: CustomFieldCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    # Verify uniqueness of field_key per entity + branch
    check_stmt = select(CustomFieldDefinition).where(
        CustomFieldDefinition.entity == payload.entity,
        CustomFieldDefinition.field_key == payload.field_key,
        CustomFieldDefinition.branch_id == payload.branch_id,
    )
    existing = (await db.execute(check_stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Custom field with key '{payload.field_key}' already exists for entity '{payload.entity}'",
        )

    cf = CustomFieldDefinition(
        id=generate_uuid(),
        branch_id=payload.branch_id,
        entity=payload.entity,
        field_key=payload.field_key,
        name=payload.name,
        field_type=payload.field_type,
        required=payload.required,
        unique=payload.unique,
        placeholder=payload.placeholder,
        default_value=payload.default_value,
        options=payload.options,
        formula_expression=payload.formula_expression,
        role_visibility=payload.role_visibility,
        conditional_display=payload.conditional_display,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
    )
    db.add(cf)
    await db.commit()
    await db.refresh(cf)

    await log_audit_event(
        db=db,
        action="CUSTOM_FIELD_CREATE",
        module="settings",
        entity="custom_field_definitions",
        entity_id=cf.id,
        actor_id=current_user.id,
        after_state={"key": cf.field_key, "name": cf.name, "entity": cf.entity, "type": cf.field_type},
    )

    return cf


@router.get("/{id}", response_model=CustomFieldResponse)
async def get_custom_field(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "VIEW_ONLY")),
):
    stmt = select(CustomFieldDefinition).where(CustomFieldDefinition.id == id)
    cf = (await db.execute(stmt)).scalar_one_or_none()
    if not cf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom field not found")
    return cf


@router.put("/{id}", response_model=CustomFieldResponse)
async def update_custom_field(
    id: str,
    payload: CustomFieldUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    stmt = select(CustomFieldDefinition).where(CustomFieldDefinition.id == id)
    cf = (await db.execute(stmt)).scalar_one_or_none()
    if not cf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom field not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(cf, key, value)

    await db.commit()
    await db.refresh(cf)

    await log_audit_event(
        db=db,
        action="CUSTOM_FIELD_UPDATE",
        module="settings",
        entity="custom_field_definitions",
        entity_id=cf.id,
        actor_id=current_user.id,
        after_state=update_data,
    )

    return cf


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_field(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    stmt = select(CustomFieldDefinition).where(CustomFieldDefinition.id == id)
    cf = (await db.execute(stmt)).scalar_one_or_none()
    if not cf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom field not found")

    await db.delete(cf)
    await db.commit()

    await log_audit_event(
        db=db,
        action="CUSTOM_FIELD_DELETE",
        module="settings",
        entity="custom_field_definitions",
        entity_id=id,
        actor_id=current_user.id,
    )


@router.post("/reorder", status_code=status.HTTP_200_OK)
async def reorder_custom_fields(
    orders: List[dict],  # [{"id": "...", "sort_order": 1}]
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "RESTRICTED")),
):
    for item in orders:
        if "id" in item and "sort_order" in item:
            await db.execute(
                update(CustomFieldDefinition)
                .where(CustomFieldDefinition.id == item["id"])
                .values(sort_order=item["sort_order"])
            )
    await db.commit()
    return {"success": True, "count": len(orders)}
