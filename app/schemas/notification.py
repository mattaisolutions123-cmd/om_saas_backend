from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class NotificationTemplateBase(BaseModel):
    name: str = Field(..., max_length=100)
    channel: str = Field("whatsapp", pattern="^(whatsapp|sms|email)$")
    category: str = Field("service_transactional")  # service_transactional, service_promotional, reminder, campaign
    dlt_template_id: Optional[str] = None
    dlt_sender_id: Optional[str] = "OMNISP"
    subject: Optional[str] = None
    body: str = Field(..., min_length=5)
    variables: List[str] = []
    is_active: bool = True


class NotificationTemplateCreate(NotificationTemplateBase):
    branch_id: Optional[str] = None


class NotificationTemplateUpdate(BaseModel):
    name: Optional[str] = None
    channel: Optional[str] = None
    category: Optional[str] = None
    dlt_template_id: Optional[str] = None
    dlt_sender_id: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    variables: Optional[List[str]] = None
    is_active: Optional[bool] = None


class NotificationTemplateResponse(NotificationTemplateBase):
    id: str
    branch_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class NotificationOptOutCreate(BaseModel):
    phone: str
    email: Optional[str] = None
    channel: str = "all"  # all, sms, whatsapp, email
    reason: Optional[str] = "Customer Opt-Out"
    source: str = "manual"  # manual, sms_keyword, unsubscribe_link, trai_dnd


class NotificationOptOutResponse(BaseModel):
    id: str
    phone: str
    email: Optional[str] = None
    channel: str
    opt_out: bool
    reason: Optional[str] = None
    source: str
    opted_out_at: datetime


class NotificationLogResponse(BaseModel):
    id: str
    branch_id: Optional[str] = None
    ticket_id: Optional[str] = None
    client_id: Optional[str] = None
    channel: str
    recipient_phone: Optional[str] = None
    recipient_email: Optional[str] = None
    template_name: Optional[str] = None
    category: str
    dlt_template_id: Optional[str] = None
    content: str
    status: str  # queued, sent, delivered, failed, read, opted_out
    vendor_message_id: Optional[str] = None
    error_reason: Optional[str] = None
    cost: float
    click_token: str
    click_target_url: Optional[str] = None
    clicked_at: Optional[datetime] = None
    click_count: int
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    created_at: datetime


class NotificationStatsResponse(BaseModel):
    total_dispatched: int
    total_delivered: int
    total_failed: int
    total_opted_out: int
    total_clicks: int
    delivery_rate_percent: float
    click_through_rate_percent: float
    by_channel: Dict[str, int]


class SendManualNotificationRequest(BaseModel):
    channel: str = Field("whatsapp", pattern="^(whatsapp|sms|email)$")
    recipient_phone: Optional[str] = None
    recipient_email: Optional[str] = None
    template_name: Optional[str] = None
    custom_content: Optional[str] = None
    variables: Dict[str, Any] = {}
    ticket_id: Optional[str] = None
    client_id: Optional[str] = None
    category: str = "service_transactional"


class PublicOptOutRequest(BaseModel):
    phone: str
    channel: str = "all"
    reason: Optional[str] = "Customer unsubscribe request"


class PublicOptOutResponse(BaseModel):
    success: bool
    message: str
    phone: str
    channel: str
