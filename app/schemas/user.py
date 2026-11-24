from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, field_validator, ValidationInfo
from app.core.rbac_constants import get_role_definition


class RolePermissionRead(BaseModel):
    module: str
    access_level: str

    class Config:
        from_attributes = True


class RoleRead(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str] = None
    is_system: bool
    permissions: List[RolePermissionRead] = []

    class Config:
        from_attributes = True


class BranchRead(BaseModel):
    id: str
    name: str
    code: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address_line: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    gstin: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


class UserRead(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    phone: Optional[str] = None
    role: Optional[RoleRead] = None
    role_slug: Optional[str] = "super_admin"
    branch: Optional[BranchRead] = None
    branch_id: Optional[str] = None
    is_active: bool
    is_superuser: bool
    must_change_password: bool = False
    last_login: Optional[datetime] = None
    preferences: Dict[str, Any] = {}
    created_at: datetime

    @field_validator("role", mode="before")
    @classmethod
    def assemble_role(cls, v: Any, info: ValidationInfo) -> Optional[Dict[str, Any]]:
        if v is None:
            slug = "super_admin"
            if info.data and "role_slug" in info.data:
                slug = info.data["role_slug"]
            return get_role_definition(slug)
        if isinstance(v, dict):
            return v
        if hasattr(v, "slug"):
            role_def = get_role_definition(getattr(v, "slug", "super_admin"))
            return {
                "id": str(getattr(v, "id", role_def.get("id"))),
                "name": str(getattr(v, "name", role_def.get("name"))),
                "slug": str(getattr(v, "slug", role_def.get("slug"))),
                "description": getattr(v, "description", role_def.get("description")),
                "is_system": bool(getattr(v, "is_system", role_def.get("is_system", True))),
                "permissions": role_def.get("permissions", []),
            }
        return None

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    phone: Optional[str] = None
    role_id: str
    branch_id: Optional[str] = None
    is_active: bool = True
