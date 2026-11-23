from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr


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
    role: Optional[Any] = None
    role_slug: Optional[str] = "super_admin"
    branch: Optional[BranchRead] = None
    branch_id: Optional[str] = None
    is_active: bool
    is_superuser: bool
    must_change_password: bool = False
    last_login: Optional[datetime] = None
    preferences: Dict[str, Any] = {}
    created_at: datetime

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
