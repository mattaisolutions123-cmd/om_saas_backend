from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class BranchBase(BaseModel):
    name: str
    code: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address_line: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    state_code: Optional[str] = Field(default="27", description="GST State Code e.g. 27, 29, 07")
    pincode: Optional[str] = None
    gstin: Optional[str] = None
    currency: str = Field(default="INR", description="Branch currency e.g. INR, USD")
    is_active: bool = True
    settings: Dict[str, Any] = Field(default_factory=dict)


class BranchCreate(BranchBase):
    pass


class BranchUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address_line: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    state_code: Optional[str] = None
    pincode: Optional[str] = None
    gstin: Optional[str] = None
    currency: Optional[str] = None
    is_active: Optional[bool] = None
    settings: Optional[Dict[str, Any]] = None


class BranchResponse(BranchBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
