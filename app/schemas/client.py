from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime


class ContactPerson(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    designation: Optional[str] = None


class BillingAddress(BaseModel):
    label: str = "Primary Address"
    address_line: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    state_code: Optional[str] = "27"
    pincode: Optional[str] = None
    gstin: Optional[str] = None
    is_default: bool = True


class AMCTerms(BaseModel):
    has_amc: bool = False
    plan_name: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    sla_hours: Optional[int] = 24


class MessagingOptIn(BaseModel):
    sms: bool = True
    whatsapp: bool = True
    email: bool = True
    promotional: bool = True


# Asset Schemas
class AssetBase(BaseModel):
    name: str = Field(..., description="e.g. MacBook Pro 14 or Maruti Swift VXi")
    brand: Optional[str] = None
    model: Optional[str] = None
    asset_type: str = "device"  # mobile, laptop, vehicle, motor, appliance, other
    identifier: str = Field(..., description="Serial number, IMEI, VIN, or Vehicle Reg No")
    dynamic_attributes: Dict[str, Any] = Field(default_factory=dict)
    warranty_status: str = "none"  # active, expired, extended, none
    warranty_expiry: Optional[datetime] = None
    purchase_date: Optional[datetime] = None
    notes: Optional[str] = None
    is_active: bool = True


class AssetCreate(AssetBase):
    client_id: Optional[str] = None
    branch_id: Optional[str] = None


class AssetUpdate(BaseModel):
    name: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    asset_type: Optional[str] = None
    identifier: Optional[str] = None
    dynamic_attributes: Optional[Dict[str, Any]] = None
    warranty_status: Optional[str] = None
    warranty_expiry: Optional[datetime] = None
    purchase_date: Optional[datetime] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class AssetResponse(AssetBase):
    id: str
    client_id: str
    branch_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Client Schemas
class ClientBase(BaseModel):
    client_type: str = Field(default="individual", description="individual or corporate")
    name: str = Field(..., description="Customer Name or Corporate Business Name")
    phone: str = Field(..., description="Primary phone number (10-digit / international)")
    email: Optional[str] = None
    contacts: List[ContactPerson] = Field(default_factory=list)
    billing_addresses: List[BillingAddress] = Field(default_factory=list)
    gstin: Optional[str] = Field(None, description="15-character Indian GSTIN (e.g. 27AAFCO1234F1Z5)")
    pan: Optional[str] = None
    credit_limit: float = 0.0
    credit_period_days: float = 0.0  # 0, 15, 30, 45, 60, 90
    discount_terms: Dict[str, Any] = Field(default_factory=dict)
    amc: AMCTerms = Field(default_factory=AMCTerms)
    tags: List[str] = Field(default_factory=list, description="VIP, difficult, prompt_payer, etc.")
    messaging_opt_in: MessagingOptIn = Field(default_factory=MessagingOptIn)
    notes: Optional[str] = None
    custom_fields: Dict[str, Any] = Field(default_factory=dict)
    branch_id: Optional[str] = None
    is_active: bool = True


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    client_type: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    contacts: Optional[List[ContactPerson]] = None
    billing_addresses: Optional[List[BillingAddress]] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    credit_limit: Optional[float] = None
    credit_period_days: Optional[float] = None
    discount_terms: Optional[Dict[str, Any]] = None
    amc: Optional[AMCTerms] = None
    tags: Optional[List[str]] = None
    messaging_opt_in: Optional[MessagingOptIn] = None
    notes: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None
    branch_id: Optional[str] = None
    is_active: Optional[bool] = None


class ClientQuickCreate(BaseModel):
    client_type: str = "individual"
    name: str
    phone: str
    email: Optional[str] = None
    branch_id: Optional[str] = None
    # Optional initial asset registered at intake / checkout
    asset_name: Optional[str] = None
    asset_identifier: Optional[str] = None
    asset_type: Optional[str] = "device"


class ClientResponse(ClientBase):
    id: str
    total_spent: float
    outstanding_balance: float
    created_at: datetime
    updated_at: datetime
    assets: List[AssetResponse] = []

    class Config:
        from_attributes = True


class ClientListResponse(BaseModel):
    items: List[ClientResponse]
    total: number if False else int
    page: int
    limit: int
    total_pages: int


# Interaction Schemas
class ClientInteractionBase(BaseModel):
    type: str = Field(default="note", description="call, sms, whatsapp, email, visit, note, status_change, payment")
    direction: str = Field(default="internal", description="inbound, outbound, internal")
    title: str
    details: Optional[str] = None
    extra_metadata: Dict[str, Any] = Field(default_factory=dict)


class ClientInteractionCreate(ClientInteractionBase):
    pass


class ClientInteractionResponse(ClientInteractionBase):
    id: str
    client_id: str
    branch_id: Optional[str] = None
    actor_id: Optional[str] = None
    actor_name: str
    actor_role: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# Financial Aging & Lifetime Value
class AgingBreakdown(BaseModel):
    current_0_30: float = 0.0
    overdue_31_60: float = 0.0
    overdue_61_90: float = 0.0
    overdue_90_plus: float = 0.0


class ClientFinancialSummary(BaseModel):
    client_id: str
    client_name: str
    total_spent: float  # Lifetime Value (LTV)
    outstanding_balance: float
    credit_limit: float
    credit_period_days: float
    credit_utilization_percent: float
    credit_status: str  # healthy, warning, exceeded
    aging: AgingBreakdown
    total_tickets: int = 0
    total_payments: int = 0
    total_assets: int = 0
