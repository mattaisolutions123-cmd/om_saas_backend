from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_permission
from app.models.user import User
from app.schemas.preset import (
    PresetSummary,
    PresetDetail,
    ApplyPresetRequest,
    ApplyPresetResponse,
)
from app.services.preset_data import INDUSTRY_PRESETS
from app.services.preset_seeder import apply_industry_preset
from app.services.audit import log_audit_event

router = APIRouter(prefix="/settings/presets", tags=["Settings - Industry Presets"])


@router.get("", response_model=List[PresetSummary])
async def list_presets(
    current_user: User = Depends(require_permission("settings", "VIEW_ONLY")),
):
    summaries = []
    for key, data in INDUSTRY_PRESETS.items():
        summaries.append(
            PresetSummary(
                key=key,
                name=data["name"],
                icon=data["icon"],
                tagline=data["tagline"],
                description=data["description"],
                custom_field_count=len(data.get("custom_fields", [])),
                pipeline_stage_count=len(data.get("pipeline", {}).get("statuses", [])),
                handbook_count=len(data.get("handbooks", [])),
                template_count=len(data.get("templates", [])),
            )
        )
    return summaries


@router.get("/{key}", response_model=PresetDetail)
async def get_preset_detail(
    key: str,
    current_user: User = Depends(require_permission("settings", "VIEW_ONLY")),
):
    if key not in INDUSTRY_PRESETS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Industry preset '{key}' not found")
    data = INDUSTRY_PRESETS[key]
    return PresetDetail(
        key=key,
        name=data["name"],
        icon=data["icon"],
        tagline=data["tagline"],
        description=data["description"],
        custom_fields=data.get("custom_fields", []),
        pipeline=data.get("pipeline", {}),
        handbooks=data.get("handbooks", []),
        catalog_items=data.get("catalog_items", []),
        templates=data.get("templates", []),
    )


@router.post("/{key}/apply", response_model=ApplyPresetResponse)
async def apply_preset(
    key: str,
    payload: ApplyPresetRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings", "FULL")),
):
    if key not in INDUSTRY_PRESETS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Industry preset '{key}' not found")

    result = await apply_industry_preset(
        db=db,
        preset_key=key,
        branch_id=payload.branch_id,
        override_existing=payload.override_existing,
    )

    await log_audit_event(
        db=db,
        action="INDUSTRY_PRESET_APPLY",
        module="settings",
        entity="presets",
        entity_id=key,
        actor_id=current_user.id,
        after_state=result,
    )

    return ApplyPresetResponse(**result)
