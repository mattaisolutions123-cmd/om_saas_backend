from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime


class StaffInviteRequest(BaseModel):
    email: EmailStr
    full_name: str
    phone: Optional[str] = None
    role_id: str
    branch_id: Optional[str] = None
    initial_password: Optional[str] = Field(default="Password@123")


class StaffUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role_id: Optional[str] = None
    branch_id: Optional[str] = None
    is_active: Optional[bool] = None


class RolePermissionUpdateRequest(BaseModel):
    role_id: str
    permissions: Dict[str, str] = Field(
        ...,
        description="Map of module -> access_level, e.g. {'trends': 'FULL', 'settings': 'RESTRICTED'}",
    )


class PermissionItem(BaseModel):
    module: str
    access_level: str


class RoleItemResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str] = None
    is_system: bool
    permissions: Dict[str, str] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class StaffUserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    phone: Optional[str] = None
    role_id: str
    role_name: Optional[str] = None
    role_slug: Optional[str] = None
    branch_id: Optional[str] = None
    branch_name: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
