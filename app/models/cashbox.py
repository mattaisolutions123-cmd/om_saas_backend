import secrets
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, String, Float, Integer, Text, JSON, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.base import TimestampMixin, generate_uuid, utc_now


class CashRegisterShift(Base, TimestampMixin):
    """
    Cash Register Shift & Blind Closeout.
    Enforces cashier binding, opening float + denominations, blind closeout,
    variance calculation, and mandatory manager audit for cash over/short.
    """
    __tablename__ = "cash_register_shifts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    shift_number = Column(String(50), unique=True, index=True, nullable=False)  # e.g. SHIFT-202611-0001
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    cashier_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    status = Column(String(20), default="OPEN", nullable=False, index=True)  # OPEN, CLOSED, LOCKED
    opened_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    # Opening float & physical denominations
    opening_float = Column(Float, default=0.0, nullable=False)
    # JSON structure: {"2000": 0, "500": 4, "200": 5, "100": 10, "50": 10, "20": 10, "10": 10, "coins": 100}
    opening_denominations = Column(JSON, default=dict, nullable=False)

    # Blind closeout counts entered by cashier
    closing_denominations = Column(JSON, default=dict, nullable=False)
    closing_counted_cash = Column(Float, default=0.0, nullable=False)

    # System calculated expected balance:
    # Expected = opening_float + cash_sales + cash_in - cash_expenses - cash_refunds
    expected_cash = Column(Float, default=0.0, nullable=False)
    variance = Column(Float, default=0.0, nullable=False)  # closing_counted_cash - expected_cash
    is_balanced = Column(Boolean, default=True, nullable=False)

    # Variance alert & manager review
    variance_reason = Column(Text, nullable=True)
    manager_override_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    notes = Column(Text, nullable=True)
    audit_meta = Column(JSON, default=dict, nullable=False)

    branch = relationship("Branch", foreign_keys=[branch_id])
    cashier = relationship("User", foreign_keys=[cashier_id])
    manager_override = relationship("User", foreign_keys=[manager_override_by_id])
    expenses = relationship("Expense", back_populates="shift")


class Account(Base, TimestampMixin):
    """
    Chart of Accounts for Double-Entry Bookkeeping.
    Standard Indian Retail accounts:
    - 1010_CASH: Cash in Register
    - 1020_UPI: UPI Digital Bank Settlement
    - 1030_CARD: POS EDC Card Settlement
    - 1040_AR: Accounts Receivable (Debtors)
    - 2010_AP: Accounts Payable (Creditors)
    - 4010_SALES: Retail & Service Sales Revenue
    - 5010_EXP_SUBCONTRACT: Vendor Subcontract Expense
    - 5020_EXP_SPARE: Spare Part Purchase Expense
    - 5030_EXP_COMMISSION: Technician Commission Expense
    - 5090_EXP_GENERAL: General & Administrative Expenses
    """
    __tablename__ = "accounts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    account_number = Column(String(50), unique=True, index=True, nullable=False)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=True, index=True)

    code = Column(String(50), index=True, nullable=False)
    name = Column(String(100), nullable=False)
    type = Column(String(20), nullable=False, index=True)  # asset, liability, equity, revenue, expense
    currency = Column(String(10), default="INR", nullable=False)
    balance = Column(Float, default=0.0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    branch = relationship("Branch", foreign_keys=[branch_id])
    entries = relationship("LedgerEntry", back_populates="account")


class LedgerEntry(Base, TimestampMixin):
    """
    Double-Entry Journal Ledger Entry.
    Every transaction consists of at least two balanced entries (Sum(Debit) == Sum(Credit))
    sharing a single transaction_group_id.
    """
    __tablename__ = "ledger_entries"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    transaction_group_id = Column(String(36), index=True, nullable=False)  # Groups debits & credits
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    shift_id = Column(String(36), ForeignKey("cash_register_shifts.id", ondelete="SET NULL"), nullable=True, index=True)
    account_id = Column(String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)

    reference_type = Column(String(30), nullable=False, index=True)  # SALE, PAYMENT, EXPENSE, REFUND, COMMISSION, TRANSFER, SHIFT_OPEN
    reference_id = Column(String(50), nullable=True, index=True)

    debit = Column(Float, default=0.0, nullable=False)
    credit = Column(Float, default=0.0, nullable=False)
    entry_date = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    narration = Column(Text, nullable=False)

    account = relationship("Account", back_populates="entries")
    branch = relationship("Branch", foreign_keys=[branch_id])
    shift = relationship("CashRegisterShift", foreign_keys=[shift_id])


class Expense(Base, TimestampMixin):
    """
    Daily Register Expense & Cash Vouchers.
    Categorized from handbook (Subcontractor, Spare Purchase, Office/Tea, Logistics, etc.).
    Spare-part cash purchase automatically provisions a stock ledger entry & inventory lot.
    """
    __tablename__ = "expenses"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    expense_number = Column(String(50), unique=True, index=True, nullable=False)  # e.g. EXP-202611-0001
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    shift_id = Column(String(36), ForeignKey("cash_register_shifts.id", ondelete="SET NULL"), nullable=True, index=True)

    category = Column(String(100), default="General", nullable=False, index=True)
    amount = Column(Float, default=0.0, nullable=False)
    payment_method = Column(String(30), default="cash", nullable=False)  # cash, upi, card, bank_transfer

    payee_name = Column(String(150), nullable=True)
    receipt_photo_url = Column(String(500), nullable=True)
    narration = Column(Text, nullable=True)

    # Subcontractor linked to ticket
    ticket_id = Column(String(36), ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True, index=True)

    # Spare Part Cash Purchase -> Auto-inventory lot creation
    is_spare_purchase = Column(Boolean, default=False, nullable=False)
    inventory_item_id = Column(String(36), ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True)
    quantity = Column(Float, default=0.0, nullable=False)
    unit_cost = Column(Float, default=0.0, nullable=False)

    created_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    branch = relationship("Branch", foreign_keys=[branch_id])
    shift = relationship("CashRegisterShift", back_populates="expenses")
    ticket = relationship("Ticket", foreign_keys=[ticket_id])
    inventory_item = relationship("InventoryItem", foreign_keys=[inventory_item_id])
    created_by = relationship("User", foreign_keys=[created_by_id])


class Refund(Base, TimestampMixin):
    """
    Customer Refund & Credit Note Settlement.
    Tracks original payment mode and adjusts double-entry ledger.
    """
    __tablename__ = "refunds"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    refund_number = Column(String(50), unique=True, index=True, nullable=False)  # e.g. REF-202611-0001
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    shift_id = Column(String(36), ForeignKey("cash_register_shifts.id", ondelete="SET NULL"), nullable=True, index=True)

    sale_id = Column(String(36), ForeignKey("sales.id", ondelete="SET NULL"), nullable=True, index=True)
    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, index=True)
    credit_note_id = Column(String(36), ForeignKey("credit_notes.id", ondelete="SET NULL"), nullable=True, index=True)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)

    original_payment_method = Column(String(30), default="cash", nullable=False)
    refund_payment_method = Column(String(30), default="cash", nullable=False)
    amount = Column(Float, default=0.0, nullable=False)
    reason = Column(String(200), default="Customer Satisfaction", nullable=False)
    status = Column(String(20), default="completed", nullable=False)  # completed, pending_approval, rejected

    approved_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)

    branch = relationship("Branch", foreign_keys=[branch_id])
    shift = relationship("CashRegisterShift", foreign_keys=[shift_id])
    sale = relationship("Sale", foreign_keys=[sale_id])
    invoice = relationship("Invoice", foreign_keys=[invoice_id])
    credit_note = relationship("CreditNote", foreign_keys=[credit_note_id])
    client = relationship("Client", foreign_keys=[client_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])


class CommissionRule(Base, TimestampMixin):
    """
    Technician Commission Engine.
    Rules:
    - flat_per_ticket: Fixed rupee reward per closed ticket (e.g. ₹200)
    - percentage_of_labor: Percentage of service labor charges (e.g. 15%)
    - tiered_monthly_volume: Scaled percentage based on cumulative monthly labor billed
    """
    __tablename__ = "commission_rules"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(100), nullable=False)
    role = Column(String(50), default="technician", nullable=False)
    technician_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    rule_type = Column(String(30), default="percentage_of_labor", nullable=False)  # flat_per_ticket, percentage_of_labor, tiered_monthly_volume
    flat_amount = Column(Float, default=0.0, nullable=False)
    labor_percentage = Column(Float, default=0.0, nullable=False)
    # Tiers configuration: [{"min_gross": 0, "max_gross": 50000, "rate": 10}, {"min_gross": 50000, "rate": 15}]
    tiers_config = Column(JSON, default=list, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    branch = relationship("Branch", foreign_keys=[branch_id])
    technician = relationship("User", foreign_keys=[technician_id])


class TechnicianCommission(Base, TimestampMixin):
    """
    Computed Commission Record per Service Ticket.
    """
    __tablename__ = "technician_commissions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    technician_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    ticket_id = Column(String(36), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_id = Column(String(36), ForeignKey("commission_rules.id", ondelete="SET NULL"), nullable=True)

    labor_amount = Column(Float, default=0.0, nullable=False)
    rate_applied = Column(String(50), default="10%", nullable=False)
    commission_amount = Column(Float, default=0.0, nullable=False)
    status = Column(String(20), default="pending", nullable=False)  # pending, approved, paid

    period_month = Column(Integer, nullable=False)
    period_year = Column(Integer, nullable=False)

    branch = relationship("Branch", foreign_keys=[branch_id])
    technician = relationship("User", foreign_keys=[technician_id])
    ticket = relationship("Ticket", foreign_keys=[ticket_id])
    rule = relationship("CommissionRule", foreign_keys=[rule_id])
