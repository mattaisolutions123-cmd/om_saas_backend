from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


# --- Payment Schemas ---

class PaymentSplitCreate(BaseModel):
    method: str = "cash"  # cash, upi, card, bank_transfer, credit
    amount: float = Field(..., gt=0)
    transaction_reference: Optional[str] = None
    notes: Optional[str] = None


class PaymentResponse(BaseModel):
    id: str
    payment_number: str
    sale_id: Optional[str] = None
    invoice_id: Optional[str] = None
    client_id: Optional[str] = None
    branch_id: str
    method: str
    amount: float
    transaction_reference: Optional[str] = None
    payment_date: datetime
    is_reconciled: bool
    reconciled_at: Optional[datetime] = None
    reconciled_by_id: Optional[str] = None
    bank_statement_reference: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentReconcilePayload(BaseModel):
    bank_statement_reference: str
    notes: Optional[str] = None


# --- Sale Line Schemas ---

class SaleLineCreate(BaseModel):
    item_type: str = "inventory"  # inventory, service
    inventory_item_id: Optional[str] = None
    service_catalog_item_id: Optional[str] = None
    name: str
    sku_or_code: Optional[str] = None
    hsn_sac_code: str = "8504"
    quantity: float = Field(default=1.0, gt=0)
    unit_price: float = Field(default=0.0, ge=0)
    discount_amount: float = 0.0
    gst_rate: float = 18.0  # 0, 5, 12, 18, 28
    warranty_days: int = 0
    serial_number: Optional[str] = None


class SaleLineResponse(BaseModel):
    id: str
    sale_id: str
    item_type: str
    inventory_item_id: Optional[str] = None
    service_catalog_item_id: Optional[str] = None
    name: str
    sku_or_code: Optional[str] = None
    hsn_sac_code: str
    quantity: float
    unit_price: float
    discount_amount: float
    taxable_amount: float
    gst_rate: float
    is_interstate: bool
    cgst_rate: float
    cgst_amount: float
    sgst_rate: float
    sgst_amount: float
    igst_rate: float
    igst_amount: float
    total_amount: float
    warranty_days: int
    serial_number: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# --- Sale Core Schemas ---

class SaleCreate(BaseModel):
    branch_id: Optional[str] = None
    client_id: Optional[str] = None
    ticket_id: Optional[str] = None
    channel: str = "counter_pos"  # counter_pos, service_order, b2b_contract, warranty_rma_zero_cost, field_onsite
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_gstin: Optional[str] = None
    customer_address: Optional[str] = None
    customer_state_code: str = "27"  # Default Maharashtra
    tax_method: str = "line_item"  # line_item, composite
    discount_type: str = "fixed"  # fixed, percentage
    discount_amount: float = 0.0
    discount_approved_by_id: Optional[str] = None
    advance_offset_amount: float = 0.0
    notes: Optional[str] = None
    lines: List[SaleLineCreate] = Field(..., min_length=1)
    payments: List[PaymentSplitCreate] = Field(default_factory=list)


class SaleResponse(BaseModel):
    id: str
    sale_number: str
    branch_id: str
    client_id: Optional[str] = None
    ticket_id: Optional[str] = None
    channel: str
    status: str
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_gstin: Optional[str] = None
    place_of_supply_state_code: str
    tax_method: str
    subtotal: float
    discount_type: str
    discount_amount: float
    discount_approved_by_id: Optional[str] = None
    cgst_amount: float
    sgst_amount: float
    igst_amount: float
    total_tax: float
    round_off: float
    grand_total: float
    advance_offset_amount: float
    paid_amount: float
    balance_due: float
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    client_name: Optional[str] = None
    branch_name: Optional[str] = None
    invoice_id: Optional[str] = None
    invoice_number: Optional[str] = None

    lines: List[SaleLineResponse] = Field(default_factory=list)
    payments: List[PaymentResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# --- Invoice Schemas ---

class InvoiceCreate(BaseModel):
    sale_id: str
    invoice_type: str = "b2c"  # b2b_tax_invoice, b2c, bill_of_supply, rcm_self_invoice
    payment_terms_days: int = 30
    billing_name: str
    billing_address: Optional[str] = None
    billing_state: str = "Maharashtra"
    billing_state_code: str = "27"
    billing_gstin: Optional[str] = None
    billing_pan: Optional[str] = None
    is_reverse_charge: bool = False
    notes: Optional[str] = None


class InvoiceResponse(BaseModel):
    id: str
    invoice_number: str
    sale_id: str
    branch_id: str
    client_id: Optional[str] = None
    invoice_type: str
    invoice_date: datetime
    due_date: datetime
    payment_terms_days: int
    status: str
    billing_name: str
    billing_address: Optional[str] = None
    billing_state: str
    billing_state_code: str
    billing_gstin: Optional[str] = None
    billing_pan: Optional[str] = None
    place_of_supply: str
    is_reverse_charge: bool
    subtotal: float
    total_tax: float
    cgst_amount: float
    sgst_amount: float
    igst_amount: float
    grand_total: float
    advance_offset: float
    amount_paid: float
    balance_due: float
    requires_eway_bill: bool
    eway_bill_number: Optional[str] = None
    eway_bill_date: Optional[datetime] = None
    irn_hash: Optional[str] = None
    irn_ack_no: Optional[str] = None
    irn_ack_date: Optional[datetime] = None
    irn_qr_code: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Delivery Challan Schemas ---

class DeliveryChallanCreate(BaseModel):
    sale_id: Optional[str] = None
    client_id: Optional[str] = None
    challan_type: str = "delivery"  # delivery, job_work, approval, demo
    transporter_name: Optional[str] = None
    vehicle_number: Optional[str] = None
    eway_bill_number: Optional[str] = None
    items: List[Dict[str, Any]] = Field(default_factory=list)
    notes: Optional[str] = None


class DeliveryChallanResponse(BaseModel):
    id: str
    challan_number: str
    sale_id: Optional[str] = None
    branch_id: str
    client_id: Optional[str] = None
    challan_type: str
    dispatch_date: datetime
    transporter_name: Optional[str] = None
    vehicle_number: Optional[str] = None
    eway_bill_number: Optional[str] = None
    status: str
    items: List[Dict[str, Any]]
    notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Credit & Debit Notes Schemas ---

class CreditNoteCreate(BaseModel):
    invoice_id: str
    reason: str = "Sales Return"  # Sales Return, Post-sale Discount, Deficiency in Service, Correction in Invoice
    taxable_amount: float = Field(..., gt=0)
    cgst_amount: float = 0.0
    sgst_amount: float = 0.0
    igst_amount: float = 0.0
    notes: Optional[str] = None


class CreditNoteResponse(BaseModel):
    id: str
    credit_note_number: str
    invoice_id: str
    branch_id: str
    client_id: Optional[str] = None
    reason: str
    taxable_amount: float
    cgst_amount: float
    sgst_amount: float
    igst_amount: float
    total_credit_amount: float
    status: str
    notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DebitNoteCreate(BaseModel):
    invoice_id: str
    reason: str = "Price Escalation"
    taxable_amount: float = Field(..., gt=0)
    cgst_amount: float = 0.0
    sgst_amount: float = 0.0
    igst_amount: float = 0.0
    notes: Optional[str] = None


class DebitNoteResponse(BaseModel):
    id: str
    debit_note_number: str
    invoice_id: str
    branch_id: str
    client_id: Optional[str] = None
    reason: str
    taxable_amount: float
    cgst_amount: float
    sgst_amount: float
    igst_amount: float
    total_debit_amount: float
    notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- AR Aging & Statutory Reports ---

class ARAgingBucket(BaseModel):
    client_id: str
    client_name: str
    client_phone: Optional[str] = None
    current_0_30: float = 0.0
    aging_31_60: float = 0.0
    aging_61_90: float = 0.0
    overdue_90_plus: float = 0.0
    total_outstanding: float = 0.0
    credit_limit: float = 0.0
    oldest_invoice_date: Optional[datetime] = None


class GSTR1Report(BaseModel):
    month_year: str
    branch_gstin: str
    branch_state_code: str
    b2b_invoices: List[Dict[str, Any]]
    b2c_large_invoices: List[Dict[str, Any]]
    b2c_small_summary: List[Dict[str, Any]]
    credit_debit_notes: List[Dict[str, Any]]
    hsn_summary: List[Dict[str, Any]]
    total_taxable_value: float
    total_cgst: float
    total_sgst: float
    total_igst: float
    total_cess: float = 0.0


class GSTR3BReport(BaseModel):
    month_year: str
    branch_gstin: str
    table_3_1_outward_supplies: Dict[str, float]
    table_3_2_interstate_unregistered: Dict[str, float]
    table_4_eligible_itc: Dict[str, float]
    net_tax_payable: Dict[str, float]
