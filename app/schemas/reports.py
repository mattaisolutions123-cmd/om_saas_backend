from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ReportColumn(BaseModel):
    key: str
    label: str
    type: str = "string"  # string, currency, number, percentage, date, badge
    align: str = "left"  # left, center, right


class ReportMetadata(BaseModel):
    report_type: str
    title: str
    description: str
    category: str  # financial, operations, inventory, staff_compliance
    columns: List[ReportColumn]
    default_chart_type: str = "bar"  # bar, line, pie, area


class ReportDataResponse(BaseModel):
    metadata: ReportMetadata
    rows: List[Dict[str, Any]]
    total_count: int
    summary_totals: Dict[str, Any]
    chart_data: List[Dict[str, Any]]


class ScheduledReportCreate(BaseModel):
    branch_id: Optional[str] = None
    report_type: str = Field(..., max_length=50)
    title: str = Field(..., min_length=3, max_length=150)
    frequency: str = Field("weekly", pattern="^(daily|weekly|monthly)$")
    export_format: str = Field("pdf", pattern="^(pdf|excel|csv)$")
    recipients: List[str] = Field(..., min_items=1)
    filters: Dict[str, Any] = {}
    is_active: bool = True


class ScheduledReportUpdate(BaseModel):
    title: Optional[str] = None
    frequency: Optional[str] = None
    export_format: Optional[str] = None
    recipients: Optional[List[str]] = None
    filters: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class ScheduledReportResponse(BaseModel):
    id: str
    branch_id: Optional[str] = None
    created_by_id: Optional[str] = None
    report_type: str
    title: str
    frequency: str
    export_format: str
    recipients: List[str]
    filters: Dict[str, Any]
    is_active: bool
    last_sent_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
