from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class PresetSummary(BaseModel):
    key: str
    name: str
    icon: str
    tagline: str
    description: str
    custom_field_count: int
    pipeline_stage_count: int
    handbook_count: int
    template_count: int


class PresetDetail(BaseModel):
    key: str
    name: str
    icon: str
    tagline: str
    description: str
    custom_fields: List[Dict[str, Any]]
    pipeline: Dict[str, Any]
    handbooks: List[Dict[str, Any]]
    catalog_items: List[Dict[str, Any]]
    templates: List[Dict[str, Any]]


class ApplyPresetRequest(BaseModel):
    branch_id: Optional[str] = Field(None, description="Optional branch to scope preset or null for global")
    override_existing: bool = Field(False, description="Whether to overwrite existing default pipelines/templates")


class ApplyPresetResponse(BaseModel):
    success: bool
    preset_key: str
    preset_name: str
    custom_fields_created: int
    pipelines_created: int
    statuses_created: int
    transitions_created: int
    handbooks_created: int
    handbook_items_created: int
    templates_created: int
    message: str
