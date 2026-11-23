from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field
from datetime import datetime


# Status Definition Schemas
class StatusDefinitionBase(BaseModel):
    name: str
    code: str
    bg_color: str = "#f1f5f9"
    text_color: str = "#0f172a"
    icon: str = "circle"
    sort_order: int = 0
    is_initial: bool = False
    is_terminal: bool = False
    is_active: bool = True


class StatusDefinitionCreate(StatusDefinitionBase):
    pipeline_id: Optional[str] = None


class StatusDefinitionUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    bg_color: Optional[str] = None
    text_color: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None
    is_initial: Optional[bool] = None
    is_terminal: Optional[bool] = None
    is_active: Optional[bool] = None


class StatusDefinitionResponse(StatusDefinitionBase):
    id: str
    pipeline_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Status Transition Schemas
class StatusTransitionBase(BaseModel):
    pipeline_id: Optional[str] = None
    from_status_id: str
    to_status_id: str
    name: Optional[str] = None
    guards: Dict[str, Any] = Field(
        default_factory=dict,
        description="Closure gate: {'closure_gate': True}, required fields: {'required_fields': [...]}, etc.",
    )
    event_hooks: Dict[str, Any] = Field(
        default_factory=dict,
        description="Event hooks: {'send_sms': {...}, 'lock_fields': [...], 'auto_create_task': {...}}",
    )
    is_active: bool = True


class StatusTransitionCreate(StatusTransitionBase):
    pass


class StatusTransitionUpdate(BaseModel):
    name: Optional[str] = None
    guards: Optional[Dict[str, Any]] = None
    event_hooks: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class StatusTransitionResponse(StatusTransitionBase):
    id: str
    pipeline_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Status Pipeline Schemas
class StatusPipelineBase(BaseModel):
    name: str
    code: str
    entity: str = "ticket"
    description: Optional[str] = None
    is_default: bool = False
    is_active: bool = True
    branch_id: Optional[str] = None


class StatusPipelineCreate(StatusPipelineBase):
    pass


class StatusPipelineUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class StatusPipelineResponse(StatusPipelineBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class StatusPipelineDetailResponse(StatusPipelineResponse):
    statuses: List[StatusDefinitionResponse] = []
    transitions: List[StatusTransitionResponse] = []


# Transition Validation Request & Response (Guards & Closure Gate)
class TransitionValidateRequest(BaseModel):
    pipeline_id: str
    from_status_id: str
    to_status_id: str
    current_balance: float = 0.0
    manager_override: bool = False
    actor_role: str = "technician"
    custom_field_values: Dict[str, Any] = Field(default_factory=dict)


class TransitionValidateResponse(BaseModel):
    allowed: bool
    transition_id: Optional[str] = None
    reasons: List[str] = []
    event_hooks: Dict[str, Any] = Field(default_factory=dict)
