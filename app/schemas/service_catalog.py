from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class ServiceCatalogItemBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    category: str = Field(default="Repair & Maintenance", max_length=100)
    sac_code: str = Field(default="9987", max_length=20)
    description: Optional[str] = None
    labor_price: float = Field(default=0.0, ge=0.0)
    duration_minutes: int = Field(default=60, ge=1)
    gst_rate: float = Field(default=18.0, ge=0.0)
    warranty_days: int = Field(default=90, ge=0)
    commission_rate: float = Field(default=0.0, ge=0.0, le=100.0)
    is_active: bool = True


class ServiceCatalogItemCreate(ServiceCatalogItemBase):
    branch_id: Optional[str] = None


class ServiceCatalogItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    sac_code: Optional[str] = None
    description: Optional[str] = None
    labor_price: Optional[float] = None
    duration_minutes: Optional[int] = None
    gst_rate: Optional[float] = None
    warranty_days: Optional[int] = None
    commission_rate: Optional[float] = None
    is_active: Optional[bool] = None


class ServiceCatalogItemResponse(ServiceCatalogItemBase):
    id: str
    branch_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ServiceCatalogListResponse(BaseModel):
    items: List[ServiceCatalogItemResponse]
    total: int
