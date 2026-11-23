from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ProgressStageItem(BaseModel):
    key: str  # received, diagnosis, repaired, ready, delivered
    label: str  # Received, Diagnosis, Repaired, Ready for Pickup, Delivered
    status: str  # completed, current, upcoming
    timestamp: Optional[datetime] = None
    description: Optional[str] = None


class SafeClientInfo(BaseModel):
    name: str
    phone_masked: str
    email_masked: Optional[str] = None


class SafeAssetInfo(BaseModel):
    brand: Optional[str] = None
    model_name: Optional[str] = None
    category: Optional[str] = None
    serial_number_masked: Optional[str] = None


class SafeBranchInfo(BaseModel):
    name: str
    phone: Optional[str] = None
    address: Optional[str] = None
    upi_vpa: str = "omnisuite@icici"
    merchant_name: str = "OmniSuite Technologies"


class BillingBreakdown(BaseModel):
    total_parts_cost: float = 0.0
    total_labor_cost: float = 0.0
    tax_total: float = 0.0
    discount_amount: float = 0.0
    grand_total: float = 0.0
    advance_deposit: float = 0.0
    paid_amount: float = 0.0
    balance_due: float = 0.0
    currency: str = "INR"


class SafeEstimateLineItem(BaseModel):
    description: str
    type: str  # part, labor
    quantity: float = 1.0
    unit_price: float = 0.0
    tax_rate: float = 18.0
    total_price: float = 0.0


class SafeEstimateInfo(BaseModel):
    id: str
    estimate_number: str
    approval_token: str
    approval_status: str  # draft, pending, approved, rejected
    parts_subtotal: float
    labor_subtotal: float
    tax_total: float
    grand_total: float
    line_items: List[Dict[str, Any]] = []
    customer_notes: Optional[str] = None
    expires_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    is_expired: bool = False


class SafeInspectionPhoto(BaseModel):
    id: str
    media_type: str  # before (pre-inspection), diagnostic_proof, after (post-repair)
    file_url: str
    file_name: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


class SafeFeedbackInfo(BaseModel):
    overall_rating: int
    technician_rating: int
    nps_score: int
    turnaround_satisfaction: str
    pricing_satisfaction: str
    comments: Optional[str] = None
    submitted_at: datetime


class PublicTrackingResponse(BaseModel):
    ticket_id: str
    ticket_number: str
    ticket_type: str
    tracking_token: str
    created_at: datetime
    promised_delivery_date: Optional[datetime] = None

    # Status & 5-Stage Live Progress
    status: str
    status_display: str
    current_stage: str  # Received, Diagnosis, Repaired, Ready, Delivered
    stage_index: int  # 0 to 4
    progress_percentage: int  # 20, 40, 60, 80, 100
    stages: List[ProgressStageItem]

    problem_reported: Optional[str] = None
    diagnosis_notes: Optional[str] = None
    qa_status: str = "pending"

    client: SafeClientInfo
    asset: Optional[SafeAssetInfo] = None
    branch: SafeBranchInfo
    billing: BillingBreakdown

    estimate: Optional[SafeEstimateInfo] = None
    photos: List[SafeInspectionPhoto] = []

    has_submitted_feedback: bool = False
    feedback: Optional[SafeFeedbackInfo] = None


# Estimate Approval / Rejection
class EstimateApprovalRequest(BaseModel):
    customer_notes: Optional[str] = None
    signature: Optional[str] = None


class EstimateApprovalResponse(BaseModel):
    success: bool
    estimate_number: str
    approval_status: str
    approved_at: datetime
    message: str


class EstimateRejectionRequest(BaseModel):
    rejection_reason: str = Field(..., min_length=3)


class EstimateRejectionResponse(BaseModel):
    success: bool
    estimate_number: str
    approval_status: str
    rejection_reason: str
    message: str


# UPI Online Payment Initiation
class UPIInitiateRequest(BaseModel):
    amount: Optional[float] = None  # If None, defaults to ticket balance_due
    notes: Optional[str] = None


class UPIInitiateResponse(BaseModel):
    transaction_ref: str
    amount: float
    currency: str = "INR"
    upi_vpa: str
    merchant_name: str
    upi_intent_url: str
    qr_code_payload: str
    ticket_number: str
    payment_links: Dict[str, str]  # GPay, PhonePe, Paytm, BHIM deep links
    status: str


# Customer Feedback Survey
class FeedbackSubmitRequest(BaseModel):
    overall_rating: int = Field(..., ge=1, le=5)
    technician_rating: int = Field(5, ge=1, le=5)
    nps_score: int = Field(10, ge=0, le=10)
    turnaround_satisfaction: str = Field("on_time")  # very_fast, on_time, delayed
    pricing_satisfaction: str = Field("fair")  # good_value, fair, expensive
    comments: Optional[str] = None
    recommend_to_others: bool = True


class FeedbackSubmitResponse(BaseModel):
    success: bool
    message: str
    submitted_at: datetime
    overall_rating: int
