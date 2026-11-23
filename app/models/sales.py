import secrets
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, String, Float, Integer, Text, JSON, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.base import TimestampMixin, generate_uuid, utc_now


class Sale(Base, TimestampMixin):
    """
    Unified Sales Entity across 5 Indian retail & commercial channels:
    1. counter_pos: In-store walk-in POS barcode checkout
    2. service_order: Billed service repair work order
    3. b2b_contract: Corporate AMC / SLA billing
    4. warranty_rma_zero_cost: Warranty return/replacement ($0 invoice)
    5. field_onsite: Technician mobile dispatch invoicing
    """
    __tablename__ = "sales"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    sale_number = Column(String(50), unique=True, index=True, nullable=False)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)

    client_id = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    ticket_id = Column(String(36), ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True, index=True)

    channel = Column(String(30), default="counter_pos", nullable=False, index=True)
    status = Column(String(30), default="completed", nullable=False, index=True)  # draft, held, confirmed, completed, cancelled

    customer_name = Column(String(150), nullable=True)
    customer_phone = Column(String(30), nullable=True)
    customer_gstin = Column(String(25), nullable=True)
    place_of_supply_state_code = Column(String(10), default="27", nullable=False)  # 2-digit GST state code

    # Tax computation method: line_item (standard per item GST) vs composite (flat rate e.g. 1% or 5% composition scheme)
    tax_method = Column(String(20), default="line_item", nullable=False)

    subtotal = Column(Float, default=0.0, nullable=False)
    discount_type = Column(String(20), default="fixed", nullable=False)  # fixed, percentage
    discount_amount = Column(Float, default=0.0, nullable=False)
    discount_approved_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Indian GST Split
    cgst_amount = Column(Float, default=0.0, nullable=False)
    sgst_amount = Column(Float, default=0.0, nullable=False)
    igst_amount = Column(Float, default=0.0, nullable=False)
    total_tax = Column(Float, default=0.0, nullable=False)
    round_off = Column(Float, default=0.0, nullable=False)
    grand_total = Column(Float, default=0.0, nullable=False)

    # Advance credit offset from work order or quote deposit
    advance_offset_amount = Column(Float, default=0.0, nullable=False)
    paid_amount = Column(Float, default=0.0, nullable=False)
    balance_due = Column(Float, default=0.0, nullable=False)

    notes = Column(Text, nullable=True)
    created_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    branch = relationship("Branch", foreign_keys=[branch_id])
    client = relationship("Client", foreign_keys=[client_id])
    ticket = relationship("Ticket", foreign_keys=[ticket_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    discount_approver = relationship("User", foreign_keys=[discount_approved_by_id])

    lines = relationship("SaleLine", back_populates="sale", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="sale", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="sale", cascade="all, delete-orphan")
    delivery_challans = relationship("DeliveryChallan", back_populates="sale", cascade="all, delete-orphan")


class SaleLine(Base, TimestampMixin):
    """
    Individual merchandise part or labor service billed on a Sale.
    """
    __tablename__ = "sale_lines"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    sale_id = Column(String(36), ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True)

    item_type = Column(String(20), default="inventory", nullable=False)  # inventory, service
    inventory_item_id = Column(String(36), ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True)
    service_catalog_item_id = Column(String(36), ForeignKey("service_catalog_items.id", ondelete="SET NULL"), nullable=True)

    name = Column(String(200), nullable=False)
    sku_or_code = Column(String(100), nullable=True)
    hsn_sac_code = Column(String(20), default="8504", nullable=False)

    quantity = Column(Float, default=1.0, nullable=False)
    unit_price = Column(Float, default=0.0, nullable=False)
    discount_amount = Column(Float, default=0.0, nullable=False)
    taxable_amount = Column(Float, default=0.0, nullable=False)

    gst_rate = Column(Float, default=18.0, nullable=False)  # 0, 5, 12, 18, 28
    is_interstate = Column(Boolean, default=False, nullable=False)
    cgst_rate = Column(Float, default=9.0, nullable=False)
    cgst_amount = Column(Float, default=0.0, nullable=False)
    sgst_rate = Column(Float, default=9.0, nullable=False)
    sgst_amount = Column(Float, default=0.0, nullable=False)
    igst_rate = Column(Float, default=0.0, nullable=False)
    igst_amount = Column(Float, default=0.0, nullable=False)
    total_amount = Column(Float, default=0.0, nullable=False)

    warranty_days = Column(Integer, default=0, nullable=False)
    serial_number = Column(String(100), nullable=True)

    sale = relationship("Sale", back_populates="lines")
    inventory_item = relationship("InventoryItem", foreign_keys=[inventory_item_id])
    service_item = relationship("ServiceCatalogItem", foreign_keys=[service_catalog_item_id])


class Invoice(Base, TimestampMixin):
    """
    Statutory GST Compliant Tax Invoice:
    1. b2b_tax_invoice: Regular GST invoice to registered business
    2. b2c: Retail end-consumer invoice
    3. bill_of_supply: For exempt items or composition dealer
    4. rcm_self_invoice: Reverse Charge Mechanism self-invoice
    """
    __tablename__ = "invoices"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    invoice_number = Column(String(50), unique=True, index=True, nullable=False)  # e.g. INV-202611-0001
    sale_id = Column(String(36), ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)

    invoice_type = Column(String(30), default="b2c", nullable=False)  # b2b_tax_invoice, b2c, bill_of_supply, rcm_self_invoice
    invoice_date = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    due_date = Column(DateTime(timezone=True), nullable=False)
    payment_terms_days = Column(Integer, default=30, nullable=False)  # 30-day AR terms default
    status = Column(String(20), default="unpaid", nullable=False, index=True)  # paid, partial, unpaid, overdue, cancelled

    # Customer & Statutory GST Details
    billing_name = Column(String(200), nullable=False)
    billing_address = Column(Text, nullable=True)
    billing_state = Column(String(100), default="Maharashtra", nullable=False)
    billing_state_code = Column(String(10), default="27", nullable=False)
    billing_gstin = Column(String(25), nullable=True, index=True)
    billing_pan = Column(String(20), nullable=True)
    place_of_supply = Column(String(10), default="27", nullable=False)
    is_reverse_charge = Column(Boolean, default=False, nullable=False)

    subtotal = Column(Float, default=0.0, nullable=False)
    total_tax = Column(Float, default=0.0, nullable=False)
    cgst_amount = Column(Float, default=0.0, nullable=False)
    sgst_amount = Column(Float, default=0.0, nullable=False)
    igst_amount = Column(Float, default=0.0, nullable=False)
    grand_total = Column(Float, default=0.0, nullable=False)

    advance_offset = Column(Float, default=0.0, nullable=False)
    amount_paid = Column(Float, default=0.0, nullable=False)
    balance_due = Column(Float, default=0.0, nullable=False)

    # Statutory Compliance: E-Way Bill (> ₹50,000 consignment threshold)
    requires_eway_bill = Column(Boolean, default=False, nullable=False)
    eway_bill_number = Column(String(50), nullable=True)
    eway_bill_date = Column(DateTime(timezone=True), nullable=True)

    # Statutory Compliance: E-Invoice IRN (> ₹5Cr B2B turnover)
    irn_hash = Column(String(100), nullable=True, index=True)
    irn_ack_no = Column(String(50), nullable=True)
    irn_ack_date = Column(DateTime(timezone=True), nullable=True)
    irn_qr_code = Column(Text, nullable=True)

    notes = Column(Text, nullable=True)

    sale = relationship("Sale", back_populates="invoices")
    branch = relationship("Branch", foreign_keys=[branch_id])
    client = relationship("Client", foreign_keys=[client_id])
    credit_notes = relationship("CreditNote", back_populates="invoice", cascade="all, delete-orphan")
    debit_notes = relationship("DebitNote", back_populates="invoice", cascade="all, delete-orphan")


class DeliveryChallan(Base, TimestampMixin):
    """
    Statutory goods movement challan without immediate tax transfer.
    Used for dispatch, job-work, or client approval before billing.
    """
    __tablename__ = "delivery_challans"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    challan_number = Column(String(50), unique=True, index=True, nullable=False)  # e.g. DC-202611-0001
    sale_id = Column(String(36), ForeignKey("sales.id", ondelete="SET NULL"), nullable=True)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True)

    challan_type = Column(String(30), default="delivery", nullable=False)  # delivery, job_work, approval, demo
    dispatch_date = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    transporter_name = Column(String(150), nullable=True)
    vehicle_number = Column(String(50), nullable=True)
    eway_bill_number = Column(String(50), nullable=True)
    status = Column(String(20), default="dispatched", nullable=False)  # dispatched, delivered, returned
    items = Column(JSON, default=list, nullable=False)
    notes = Column(Text, nullable=True)

    sale = relationship("Sale", back_populates="delivery_challans")
    branch = relationship("Branch", foreign_keys=[branch_id])
    client = relationship("Client", foreign_keys=[client_id])


class CreditNote(Base, TimestampMixin):
    """
    Statutory Credit Note under Section 34 of CGST Act for sales return or post-sale discount.
    """
    __tablename__ = "credit_notes"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    credit_note_number = Column(String(50), unique=True, index=True, nullable=False)  # e.g. CN-202611-0001
    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True)

    reason = Column(String(100), default="Sales Return", nullable=False)  # Sales Return, Post-sale Discount, Deficiency in Service, Correction in Invoice
    taxable_amount = Column(Float, default=0.0, nullable=False)
    cgst_amount = Column(Float, default=0.0, nullable=False)
    sgst_amount = Column(Float, default=0.0, nullable=False)
    igst_amount = Column(Float, default=0.0, nullable=False)
    total_credit_amount = Column(Float, default=0.0, nullable=False)

    status = Column(String(20), default="active", nullable=False)  # active, adjusted, refunded
    notes = Column(Text, nullable=True)

    invoice = relationship("Invoice", back_populates="credit_notes")
    branch = relationship("Branch", foreign_keys=[branch_id])
    client = relationship("Client", foreign_keys=[client_id])


class DebitNote(Base, TimestampMixin):
    """
    Statutory Debit Note for price escalation or extra quantities under CGST Act.
    """
    __tablename__ = "debit_notes"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    debit_note_number = Column(String(50), unique=True, index=True, nullable=False)  # e.g. DN-202611-0001
    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True)

    reason = Column(String(100), default="Price Escalation", nullable=False)
    taxable_amount = Column(Float, default=0.0, nullable=False)
    cgst_amount = Column(Float, default=0.0, nullable=False)
    sgst_amount = Column(Float, default=0.0, nullable=False)
    igst_amount = Column(Float, default=0.0, nullable=False)
    total_debit_amount = Column(Float, default=0.0, nullable=False)
    notes = Column(Text, nullable=True)

    invoice = relationship("Invoice", back_populates="debit_notes")
    branch = relationship("Branch", foreign_keys=[branch_id])
    client = relationship("Client", foreign_keys=[client_id])


class Payment(Base, TimestampMixin):
    """
    Multi-tender Split Payment & Bank Reconciliation.
    Supports split methods: cash, upi, card, bank_transfer, credit.
    Includes reconciliation flags for NEFT/RTGS bank matching.
    """
    __tablename__ = "payments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    payment_number = Column(String(50), unique=True, index=True, nullable=False)  # e.g. PAY-202611-0001
    sale_id = Column(String(36), ForeignKey("sales.id", ondelete="SET NULL"), nullable=True, index=True)
    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, index=True)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)

    method = Column(String(30), default="cash", nullable=False)  # cash, upi, card, bank_transfer, credit
    amount = Column(Float, default=0.0, nullable=False)
    transaction_reference = Column(String(100), nullable=True)  # UPI UTR, Card Auth Code, Cheque No, NEFT Ref
    payment_date = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Bank Reconciliation Fields (NEFT / RTGS / UTR Matching)
    is_reconciled = Column(Boolean, default=False, nullable=False)
    reconciled_at = Column(DateTime(timezone=True), nullable=True)
    reconciled_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    bank_statement_reference = Column(String(100), nullable=True)

    notes = Column(Text, nullable=True)

    sale = relationship("Sale", back_populates="payments")
    invoice = relationship("Invoice")
    client = relationship("Client")
    branch = relationship("Branch")
    reconciled_by = relationship("User", foreign_keys=[reconciled_by_id])
