from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# 1. Denominations
class DenominationsMap(BaseModel):
    two_thousand: int = Field(default=0, alias="2000")
    five_hundred: int = Field(default=0, alias="500")
    two_hundred: int = Field(default=0, alias="200")
    one_hundred: int = Field(default=0, alias="100")
    fifty: int = Field(default=0, alias="50")
    twenty: int = Field(default=0, alias="20")
    ten: int = Field(default=0, alias="10")
    coins: float = Field(default=0.0)

    class Config:
        populate_by_name = True


# 2. Cash Register Shift
class CashRegisterShiftOpen(BaseModel):
    branch_id: str
    cashier_id: str
    opening_float: float = Field(ge=0.0)
    opening_denominations: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None


class CashRegisterShiftClose(BaseModel):
    closing_denominations: Dict[str, Any]
    closing_counted_cash: float = Field(ge=0.0)
    variance_reason: Optional[str] = None
    manager_override_by_id: Optional[str] = None
    notes: Optional[str] = None


class CashRegisterShiftResponse(BaseModel):
    id: str
    shift_number: str
    branch_id: str
    cashier_id: str
    status: str
    opened_at: datetime
    closed_at: Optional[datetime] = None
    opening_float: float
    opening_denominations: Dict[str, Any]
    closing_denominations: Dict[str, Any]
    closing_counted_cash: float
    expected_cash: float
    variance: float
    is_balanced: bool
    variance_reason: Optional[str] = None
    manager_override_by_id: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    cashier_name: Optional[str] = None
    branch_name: Optional[str] = None

    class Config:
        from_attributes = True


# 3. Account
class AccountCreate(BaseModel):
    branch_id: Optional[str] = None
    code: str
    name: str
    type: str  # asset, liability, equity, revenue, expense
    currency: str = "INR"
    balance: float = 0.0


class AccountResponse(BaseModel):
    id: str
    account_number: str
    branch_id: Optional[str] = None
    code: str
    name: str
    type: str
    currency: str
    balance: float
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# 4. Ledger Entry (Double Entry)
class LedgerLineItem(BaseModel):
    account_id: str
    debit: float = 0.0
    credit: float = 0.0
    narration: str


class LedgerBatchCreate(BaseModel):
    branch_id: str
    shift_id: Optional[str] = None
    reference_type: str  # SALE, PAYMENT, EXPENSE, REFUND, COMMISSION, TRANSFER, SHIFT_OPEN
    reference_id: Optional[str] = None
    entries: List[LedgerLineItem]


class LedgerEntryResponse(BaseModel):
    id: str
    transaction_group_id: str
    branch_id: str
    shift_id: Optional[str] = None
    account_id: str
    account_code: Optional[str] = None
    account_name: Optional[str] = None
    reference_type: str
    reference_id: Optional[str] = None
    debit: float
    credit: float
    entry_date: datetime
    narration: str
    created_at: datetime

    class Config:
        from_attributes = True


# 5. Expense
class ExpenseCreate(BaseModel):
    branch_id: str
    shift_id: Optional[str] = None
    category: str  # Subcontractor, Spare Purchase, Logistics, etc.
    amount: float = Field(gt=0.0)
    payment_method: str = "cash"  # cash, upi, card, bank_transfer
    payee_name: Optional[str] = None
    receipt_photo_url: Optional[str] = None
    narration: Optional[str] = None
    ticket_id: Optional[str] = None

    # Spare Part Cash Purchase auto-inventory lot creation
    is_spare_purchase: bool = False
    inventory_item_id: Optional[str] = None
    quantity: float = 0.0
    unit_cost: float = 0.0


class ExpenseResponse(BaseModel):
    id: str
    expense_number: str
    branch_id: str
    shift_id: Optional[str] = None
    category: str
    amount: float
    payment_method: str
    payee_name: Optional[str] = None
    receipt_photo_url: Optional[str] = None
    narration: Optional[str] = None
    ticket_id: Optional[str] = None
    is_spare_purchase: bool
    inventory_item_id: Optional[str] = None
    quantity: float
    unit_cost: float
    created_by_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# 6. Refund
class RefundCreate(BaseModel):
    branch_id: str
    shift_id: Optional[str] = None
    sale_id: Optional[str] = None
    invoice_id: Optional[str] = None
    credit_note_id: Optional[str] = None
    client_id: Optional[str] = None
    original_payment_method: str = "cash"
    refund_payment_method: str = "cash"
    amount: float = Field(gt=0.0)
    reason: str = "Customer Return"
    notes: Optional[str] = None


class RefundResponse(BaseModel):
    id: str
    refund_number: str
    branch_id: str
    shift_id: Optional[str] = None
    sale_id: Optional[str] = None
    invoice_id: Optional[str] = None
    credit_note_id: Optional[str] = None
    client_id: Optional[str] = None
    original_payment_method: str
    refund_payment_method: str
    amount: float
    reason: str
    status: str
    approved_by_id: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# 7. Commission Rules & Payroll
class CommissionRuleCreate(BaseModel):
    branch_id: Optional[str] = None
    name: str
    role: str = "technician"
    technician_id: Optional[str] = None
    rule_type: str = "percentage_of_labor"  # flat_per_ticket, percentage_of_labor, tiered_monthly_volume
    flat_amount: float = 0.0
    labor_percentage: float = 0.0
    tiers_config: List[Dict[str, Any]] = Field(default_factory=list)
    is_active: bool = True


class CommissionRuleResponse(BaseModel):
    id: str
    branch_id: Optional[str] = None
    name: str
    role: str
    technician_id: Optional[str] = None
    rule_type: str
    flat_amount: float
    labor_percentage: float
    tiers_config: List[Dict[str, Any]]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class PayrollReportItem(BaseModel):
    technician_id: str
    technician_name: str
    tickets_completed: int
    gross_labor_billed: float
    total_commission_earned: float
    status: str


class PayrollReportResponse(BaseModel):
    period_month: int
    period_year: int
    branch_id: Optional[str] = None
    technicians: List[PayrollReportItem]
    total_payroll_commission: float


# 8. Profitability per Ticket
class ProfitPerTicketResponse(BaseModel):
    ticket_id: str
    ticket_number: str
    total_bill: float
    parts_cost: float
    subcontract_expenses: float
    tech_commission: float
    net_profit: float
    margin_percentage: float


# 9. Multi-branch Consolidation
class BranchFinancialSummary(BaseModel):
    branch_id: str
    branch_name: str
    cash_balance: float
    bank_upi_balance: float
    receivables_balance: float
    total_revenue: float
    total_expenses: float
    net_profit: float


class ConsolidatedFinancialsResponse(BaseModel):
    consolidated_at: datetime
    branches: List[BranchFinancialSummary]
    total_cash: float
    total_bank_upi: float
    total_receivables: float
    total_revenue: float
    total_expenses: float
    net_consolidated_profit: float


# 10. UPI Webhook Payload
class UpiWebhookPayload(BaseModel):
    event: str = "payment.success"
    transaction_id: str  # Bank reference / UTR
    amount: float
    payer_vpa: Optional[str] = None
    merchant_transaction_id: str  # ticket_id, invoice_id, or sale_id
    status: str = "SUCCESS"
    timestamp: Optional[datetime] = None


class UpiWebhookResponse(BaseModel):
    success: bool
    message: str
    matched_entity: Optional[str] = None
    payment_id: Optional[str] = None
