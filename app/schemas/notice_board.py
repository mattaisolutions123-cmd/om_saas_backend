from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class NoticeResponseBase(BaseModel):
    quote_amount: Optional[float] = None
    message: str = Field(..., min_length=2)
    estimated_delivery_days: Optional[int] = None


class NoticeResponseCreate(NoticeResponseBase):
    pass


class NoticeResponseItem(NoticeResponseBase):
    id: str
    post_id: str
    responder_id: str
    responder_name: Optional[str] = None
    responder_role: Optional[str] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class NoticeBoardPostBase(BaseModel):
    category: str = Field("subcontracting", description="subcontracting, spare_sourcing, internal_notice, equipment_exchange, urgent_help")
    title: str = Field(..., min_length=3, max_length=250)
    description: str = Field(..., min_length=5)
    urgency: str = Field("normal", description="low, normal, high, critical")
    budget_or_price: Optional[float] = None
    currency: str = "INR"
    part_number_or_sku: Optional[str] = None
    device_model: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    location_city: Optional[str] = "Mumbai"
    branch_id: Optional[str] = None
    expires_at: Optional[datetime] = None
    attachments: List[str] = []


class NoticeBoardPostCreate(NoticeBoardPostBase):
    pass


class NoticeBoardPostUpdate(BaseModel):
    category: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    urgency: Optional[str] = None
    status: Optional[str] = None
    budget_or_price: Optional[float] = None
    part_number_or_sku: Optional[str] = None
    device_model: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    location_city: Optional[str] = None
    expires_at: Optional[datetime] = None
    attachments: Optional[List[str]] = None


class NoticeBoardPostResponse(NoticeBoardPostBase):
    id: str
    author_id: str
    author_name: Optional[str] = None
    author_role: Optional[str] = None
    branch_name: Optional[str] = None
    status: str
    responses_count: int = 0
    responses: List[NoticeResponseItem] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
