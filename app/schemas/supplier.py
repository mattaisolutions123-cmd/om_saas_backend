from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class SupplierBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    supplier_type: str = Field(default="legal_entity", pattern="^(individual|legal_entity)$")
    contact_name: Optional[str] = None
    phone: str = Field(..., min_length=10, max_length=30)
    email: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    credit_period_days: int = Field(default=30, ge=0)
    credit_limit: float = Field(default=0.0, ge=0.0)
    payment_terms: str = Field(default="Net 30", max_length=100)
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    state_code: Optional[str] = None
    pincode: Optional[str] = None
    bank_details: Dict[str, Any] = Field(default_factory=dict)
    rating: float = Field(default=5.0, ge=1.0, le=5.0)
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    is_active: bool = True


class SupplierCreate(SupplierBase):
    branch_id: Optional[str] = None


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    supplier_type: Optional[str] = None
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    credit_period_days: Optional[int] = None
    credit_limit: Optional[float] = None
    payment_terms: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    state_code: Optional[str] = None
    pincode: Optional[str] = None
    bank_details: Optional[Dict[str, Any]] = None
    rating: Optional[float] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class SupplierResponse(SupplierBase):
    id: str
    branch_id: Optional[str] = None
    total_orders_count: int = 0
    total_purchases_amount: float = 0.0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SupplierListResponse(BaseModel):
    items: List[SupplierResponse]
    total: int
