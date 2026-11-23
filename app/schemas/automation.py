from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class AutomationRuleResponse(BaseModel):
    id: str
    branch_id: Optional[str] = None
    name: str
    code: str
    trigger_event: str
    delay_hours: int
    delay_days: int
    advance_days: int
    channel: str
    template_name: str
    conditions: Dict[str, Any]
    is_active: bool
    execution_count: int
    last_run_at: Optional[datetime] = None
    created_at: datetime


class AutomationRuleUpdate(BaseModel):
    name: Optional[str] = None
    channel: Optional[str] = None
    delay_hours: Optional[int] = None
    delay_days: Optional[int] = None
    advance_days: Optional[int] = None
    template_name: Optional[str] = None
    conditions: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class ScheduledJobResponse(BaseModel):
    id: str
    rule_id: Optional[str] = None
    ticket_id: Optional[str] = None
    client_id: str
    asset_id: Optional[str] = None
    job_type: str
    scheduled_for: datetime
    status: str
    executed_at: Optional[datetime] = None
    execution_result: Dict[str, Any]
    created_at: datetime


class RunAutomationResponse(BaseModel):
    processed_count: int
    executed_count: int
    opted_out_count: int
    failed_count: int
    jobs_summary: List[Dict[str, Any]] = []


# Marketing Campaigns & Audience Segments
class MarketingCampaignCreate(BaseModel):
    branch_id: Optional[str] = None
    name: str = Field(..., min_length=3, max_length=150)
    channel: str = Field("whatsapp", pattern="^(whatsapp|sms|email)$")
    segment_type: str = Field("all")  # all, high_value, inactive_90d, warranty_expired, brand_specific, pin_code_cluster
    segment_criteria: Dict[str, Any] = {}
    template_id: Optional[str] = None
    custom_message: Optional[str] = None
    scheduled_at: Optional[datetime] = None


class MarketingCampaignUpdate(BaseModel):
    name: Optional[str] = None
    channel: Optional[str] = None
    segment_type: Optional[str] = None
    segment_criteria: Optional[Dict[str, Any]] = None
    template_id: Optional[str] = None
    custom_message: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    status: Optional[str] = None


class MarketingCampaignResponse(BaseModel):
    id: str
    branch_id: Optional[str] = None
    name: str
    channel: str
    segment_type: str
    segment_criteria: Dict[str, Any]
    template_id: Optional[str] = None
    custom_message: Optional[str] = None
    status: str
    scheduled_at: Optional[datetime] = None
    sent_count: int
    delivered_count: int
    failed_count: int
    clicked_count: int
    opt_out_count: int
    created_at: datetime


class SegmentPreviewRequest(BaseModel):
    segment_type: str = "all"
    segment_criteria: Dict[str, Any] = {}
    branch_id: Optional[str] = None


class SegmentClientItem(BaseModel):
    id: str
    name: str
    phone: str
    email: Optional[str] = None
    total_spent: float
    last_ticket_date: Optional[datetime] = None
    is_opted_out: bool = False


class SegmentPreviewResponse(BaseModel):
    segment_type: str
    total_matches: int
    eligible_count: int  # After scrubbing DLT opt-outs
    opted_out_count: int
    sample_clients: List[SegmentClientItem] = []
