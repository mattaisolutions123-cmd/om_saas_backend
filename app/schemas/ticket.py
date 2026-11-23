from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


# --- Ticket Part Schemas ---

class TicketPartCreate(BaseModel):
    inventory_item_id: str
    quantity: float = Field(default=1.0, gt=0)
    unit_price: Optional[float] = None  # If None, defaults to retail_price from inventory_item
    tax_rate: Optional[float] = None    # If None, defaults to tax_rate from inventory_item
    notes: Optional[str] = None


class TicketPartResponse(BaseModel):
    id: str
    ticket_id: str
    inventory_item_id: str
    item_name: Optional[str] = None
    item_sku: Optional[str] = None
    quantity: float
    unit_cost: float
    unit_price: float
    tax_rate: float
    total_price: float
    is_reserved: bool
    reservation_id: Optional[str] = None
    is_consumed: bool
    consumed_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Ticket Labor Schemas ---

class TicketLaborCreate(BaseModel):
    service_catalog_item_id: Optional[str] = None
    name: str
    sac_code: Optional[str] = "9987"
    labor_price: float = Field(default=0.0, ge=0)
    tax_rate: Optional[float] = 18.0
    commission_rate: Optional[float] = 0.0
    assigned_tech_id: Optional[str] = None
    duration_minutes: Optional[int] = 30


class TicketLaborResponse(BaseModel):
    id: str
    ticket_id: str
    service_catalog_item_id: Optional[str] = None
    name: str
    sac_code: str
    labor_price: float
    tax_rate: float
    total_price: float
    commission_rate: float
    commission_amount: float
    assigned_tech_id: Optional[str] = None
    assigned_tech_name: Optional[str] = None
    duration_minutes: int
    status: str
    completed_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Ticket Media Schemas ---

class TicketMediaCreate(BaseModel):
    media_type: str = "before"  # before, after, diagnostic_proof
    file_url: str
    file_name: Optional[str] = None
    file_size_kb: Optional[int] = 0
    notes: Optional[str] = None


class TicketMediaResponse(BaseModel):
    id: str
    ticket_id: str
    media_type: str
    file_url: str
    file_name: Optional[str] = None
    file_size_kb: int
    notes: Optional[str] = None
    uploaded_by_id: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Ticket Estimate Schemas ---

class TicketEstimateCreate(BaseModel):
    customer_notes: Optional[str] = None
    line_items: Optional[List[Dict[str, Any]]] = None  # If omitted, auto-generated from ticket parts & labor


class TicketEstimateResponse(BaseModel):
    id: str
    ticket_id: str
    estimate_number: str
    approval_token: str
    approval_status: str
    parts_subtotal: float
    labor_subtotal: float
    tax_total: float
    grand_total: float
    line_items: List[Dict[str, Any]] = Field(default_factory=list)
    customer_notes: Optional[str] = None
    approved_at: Optional[datetime] = None
    customer_ip: Optional[str] = None
    rejection_reason: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EstimateApprovalPayload(BaseModel):
    action: str  # approve, reject
    rejection_reason: Optional[str] = None


# --- Subcontract Schemas ---

class TicketSubcontractCreate(BaseModel):
    vendor_name: str
    vendor_phone: Optional[str] = None
    task_description: str
    cost: float = Field(default=0.0, ge=0)
    charged_to_customer: float = Field(default=0.0, ge=0)
    expected_return_date: Optional[datetime] = None
    notes: Optional[str] = None


class TicketSubcontractUpdate(BaseModel):
    status: Optional[str] = None  # dispatched, in_progress, returned, cancelled
    cost: Optional[float] = None
    charged_to_customer: Optional[float] = None
    actual_return_date: Optional[datetime] = None
    notes: Optional[str] = None


class TicketSubcontractResponse(BaseModel):
    id: str
    ticket_id: str
    vendor_name: str
    vendor_phone: Optional[str] = None
    task_description: str
    cost: float
    charged_to_customer: float
    status: str
    dispatch_date: Optional[datetime] = None
    expected_return_date: Optional[datetime] = None
    actual_return_date: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- QA Checklist Schemas ---

class QAChecklistUpdate(BaseModel):
    qa_status: str  # pending, passed, failed
    qa_checklist: List[Dict[str, Any]]  # [{"id": "1", "label": "Screen touch test", "checked": true, "notes": "OK"}]


# --- Handover & Settlement ---

class TicketHandoverPayload(BaseModel):
    handover_recipient: str
    handover_signature: Optional[str] = None
    payment_method: str = "cash"  # cash, upi, card, bank_transfer
    payment_amount: float = Field(default=0.0, ge=0)
    manager_override: bool = False
    notes: Optional[str] = None


# --- Ticket Core CRUD Schemas ---

class TicketCreate(BaseModel):
    branch_id: Optional[str] = None
    client_id: str
    asset_id: Optional[str] = None
    ticket_type: str = "service"  # service, warranty_rma, offsite
    pipeline_id: Optional[str] = None
    status: Optional[str] = "intake"
    priority: str = "standard"  # low, standard, high, urgent
    assigned_tech_id: Optional[str] = None
    intake_source: str = "counter"  # counter, phone, online, onsite, field
    intake_notes: Optional[str] = None
    problem_reported: Optional[str] = None
    diagnosis_notes: Optional[str] = None
    promised_delivery_date: Optional[datetime] = None
    customer_max_repair_budget: float = 0.0
    advance_deposit: float = 0.0
    dynamic_fields: Dict[str, Any] = Field(default_factory=dict)
    rma_details: Dict[str, Any] = Field(default_factory=dict)


class TicketUpdate(BaseModel):
    ticket_type: Optional[str] = None
    pipeline_id: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_tech_id: Optional[str] = None
    intake_source: Optional[str] = None
    intake_notes: Optional[str] = None
    problem_reported: Optional[str] = None
    diagnosis_notes: Optional[str] = None
    promised_delivery_date: Optional[datetime] = None
    customer_max_repair_budget: Optional[float] = None
    advance_deposit: Optional[float] = None
    is_paused: Optional[bool] = None
    pause_reason: Optional[str] = None
    dynamic_fields: Optional[Dict[str, Any]] = None
    rma_details: Optional[Dict[str, Any]] = None
    manager_override: bool = False


class TicketResponse(BaseModel):
    id: str
    ticket_number: str
    branch_id: str
    client_id: str
    asset_id: Optional[str] = None
    ticket_type: str
    pipeline_id: Optional[str] = None
    status: str
    priority: str
    assigned_tech_id: Optional[str] = None
    intake_source: str
    intake_notes: Optional[str] = None
    problem_reported: Optional[str] = None
    diagnosis_notes: Optional[str] = None
    promised_delivery_date: Optional[datetime] = None
    customer_max_repair_budget: float
    advance_deposit: float
    total_parts_cost: float
    total_labor_cost: float
    tax_total: float
    discount_amount: float
    grand_total: float
    paid_amount: float
    balance_due: float
    is_paused: bool
    pause_reason: Optional[str] = None
    tracking_token: str
    dynamic_fields: Dict[str, Any] = Field(default_factory=dict)
    qa_status: str
    qa_checklist: List[Dict[str, Any]] = Field(default_factory=list)
    rma_details: Dict[str, Any] = Field(default_factory=dict)
    handover_at: Optional[datetime] = None
    handover_signature: Optional[str] = None
    handover_recipient: Optional[str] = None
    handover_notes: Optional[str] = None
    created_by_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Expanded / joined metadata for desk & mobile view
    client_name: Optional[str] = None
    client_phone: Optional[str] = None
    asset_name: Optional[str] = None
    asset_identifier: Optional[str] = None
    assigned_tech_name: Optional[str] = None
    branch_name: Optional[str] = None

    parts: List[TicketPartResponse] = Field(default_factory=list)
    labor_items: List[TicketLaborResponse] = Field(default_factory=list)
    media: List[TicketMediaResponse] = Field(default_factory=list)
    estimates: List[TicketEstimateResponse] = Field(default_factory=list)
    subcontracts: List[TicketSubcontractResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# --- Public Tracking Response (Cleaned / Non-Confidential) ---

class TicketPublicTrackingResponse(BaseModel):
    ticket_number: str
    status: str
    priority: str
    ticket_type: str
    problem_reported: Optional[str] = None
    diagnosis_notes: Optional[str] = None
    promised_delivery_date: Optional[datetime] = None
    grand_total: float
    paid_amount: float
    balance_due: float
    is_paused: bool
    pause_reason: Optional[str] = None
    qa_status: str
    created_at: datetime
    updated_at: datetime
    client_name: Optional[str] = None
    asset_name: Optional[str] = None
    asset_identifier: Optional[str] = None
    branch_name: Optional[str] = None
    estimates: List[TicketEstimateResponse] = Field(default_factory=list)
    before_media_urls: List[str] = Field(default_factory=list)
    after_media_urls: List[str] = Field(default_factory=list)
