from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field
from datetime import datetime


class CustomFieldBase(BaseModel):
    entity: str = Field(..., description="Target entity: ticket, client, inventory, supplier, task")
    field_key: str = Field(..., description="Normalized field key, e.g. device_serial")
    name: str = Field(..., description="Field label shown to user")
    field_type: str = Field(
        ...,
        description="One of: short_text, long_text, number, dropdown, multi_select, date_time, currency, checkbox, image_upload, signature_pad, barcode_scan, formula",
    )
    required: bool = False
    unique: bool = False
    placeholder: Optional[str] = None
    default_value: Optional[Any] = None
    options: List[Dict[str, Any]] = Field(default_factory=list, description="Dropdown/Multi-select choices")
    formula_expression: Optional[Dict[str, Any]] = None
    role_visibility: List[str] = Field(default_factory=list, description="Role slugs allowed to view/edit")
    conditional_display: Optional[Dict[str, Any]] = None
    sort_order: int = 0
    is_active: bool = True
    branch_id: Optional[str] = None


class CustomFieldCreate(CustomFieldBase):
    pass


class CustomFieldUpdate(BaseModel):
    name: Optional[str] = None
    field_type: Optional[str] = None
    required: Optional[bool] = None
    unique: Optional[bool] = None
    placeholder: Optional[str] = None
    default_value: Optional[Any] = None
    options: Optional[List[Dict[str, Any]]] = None
    formula_expression: Optional[Dict[str, Any]] = None
    role_visibility: Optional[List[str]] = None
    conditional_display: Optional[Dict[str, Any]] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class CustomFieldResponse(CustomFieldBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
