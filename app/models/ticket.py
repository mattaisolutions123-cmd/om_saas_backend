import secrets
from sqlalchemy import Boolean, Column, String, Float, Integer, Text, JSON, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.base import TimestampMixin, generate_uuid, utc_now


def generate_tracking_token() -> str:
    """Generate a 128-bit secure random hex string for public tracking and estimate tokenization."""
    return secrets.token_hex(16)  # 16 bytes = 128 bits = 32 hex chars


class Ticket(Base, TimestampMixin):
    """
    Core Work Order / Service / Warranty RMA / Offsite Repair Ticket.
    """
    __tablename__ = "tickets"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    ticket_number = Column(String(50), unique=True, index=True, nullable=False)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)

    client_id = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id = Column(String(36), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True, index=True)

    # Ticket Type: service, warranty_rma, offsite
    ticket_type = Column(String(30), default="service", nullable=False, index=True)

    # Pipeline & Status
    pipeline_id = Column(String(36), ForeignKey("status_pipelines.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String(50), default="intake", nullable=False, index=True)
    priority = Column(String(20), default="standard", nullable=False, index=True)  # low, standard, high, urgent

    # Assignment & Intake
    assigned_tech_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    intake_source = Column(String(50), default="counter", nullable=False)  # counter, phone, online, onsite, field
    intake_notes = Column(Text, nullable=True)
    problem_reported = Column(Text, nullable=True)
    diagnosis_notes = Column(Text, nullable=True)

    # Dates
    promised_delivery_date = Column(DateTime(timezone=True), nullable=True)

    # Commercial & Threshold Pauses
    customer_max_repair_budget = Column(Float, default=0.0, nullable=False)  # If estimate/cost exceeds this, pause for approval
    advance_deposit = Column(Float, default=0.0, nullable=False)
    total_parts_cost = Column(Float, default=0.0, nullable=False)
    total_labor_cost = Column(Float, default=0.0, nullable=False)
    tax_total = Column(Float, default=0.0, nullable=False)
    discount_amount = Column(Float, default=0.0, nullable=False)
    grand_total = Column(Float, default=0.0, nullable=False)
    paid_amount = Column(Float, default=0.0, nullable=False)
    balance_due = Column(Float, default=0.0, nullable=False)

    # Pause state (e.g. threshold exceeded, spare part waiting, customer hold)
    is_paused = Column(Boolean, default=False, nullable=False)
    pause_reason = Column(String(255), nullable=True)

    # 128-bit public tracking token
    tracking_token = Column(String(64), unique=True, default=generate_tracking_token, nullable=False, index=True)

    # Dynamic JSONB Custom Fields (compatible with CustomFieldDefinitions for entity="ticket")
    dynamic_fields = Column(JSON, default=dict, nullable=False)

    # Quality Assurance (QA) Checklist
    qa_status = Column(String(20), default="pending", nullable=False)  # pending, passed, failed
    qa_checklist = Column(JSON, default=list, nullable=False)  # [{"id": "...", "label": "...", "checked": True, "notes": "..."}]

    # RMA / Warranty claim metadata
    rma_details = Column(JSON, default=dict, nullable=False)  # {"original_invoice_no": "...", "vendor_claim_no": "...", "claim_type": "replacement"}

    # Handover & Settlement
    handover_at = Column(DateTime(timezone=True), nullable=True)
    handover_signature = Column(Text, nullable=True)  # Canvas signature data URL
    handover_recipient = Column(String(150), nullable=True)
    handover_notes = Column(Text, nullable=True)

    created_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    branch = relationship("Branch", foreign_keys=[branch_id])
    client = relationship("Client", foreign_keys=[client_id])
    asset = relationship("Asset", foreign_keys=[asset_id])
    assigned_tech = relationship("User", foreign_keys=[assigned_tech_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    pipeline = relationship("StatusPipeline", foreign_keys=[pipeline_id])

    parts = relationship("TicketPart", back_populates="ticket", cascade="all, delete-orphan")
    labor_items = relationship("TicketLabor", back_populates="ticket", cascade="all, delete-orphan")
    media = relationship("TicketMedia", back_populates="ticket", cascade="all, delete-orphan")
    estimates = relationship("TicketEstimate", back_populates="ticket", cascade="all, delete-orphan")
    subcontracts = relationship("TicketSubcontract", back_populates="ticket", cascade="all, delete-orphan")


class TicketPart(Base, TimestampMixin):
    """
    Parts/materials allocated and consumed for a ticket.
    Integrates with StockReservation and StockLedger.
    """
    __tablename__ = "ticket_parts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    ticket_id = Column(String(36), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    inventory_item_id = Column(String(36), ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False, index=True)

    quantity = Column(Float, default=1.0, nullable=False)
    unit_cost = Column(Float, default=0.0, nullable=False)  # Acquisition cost from inventory
    unit_price = Column(Float, default=0.0, nullable=False)  # Selling price billed to client
    tax_rate = Column(Float, default=18.0, nullable=False)
    total_price = Column(Float, default=0.0, nullable=False)

    is_reserved = Column(Boolean, default=True, nullable=False)
    reservation_id = Column(String(36), ForeignKey("stock_reservations.id", ondelete="SET NULL"), nullable=True)
    is_consumed = Column(Boolean, default=False, nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    ticket = relationship("Ticket", back_populates="parts")
    item = relationship("InventoryItem", foreign_keys=[inventory_item_id])
    reservation = relationship("StockReservation", foreign_keys=[reservation_id])


class TicketLabor(Base, TimestampMixin):
    """
    Labor and technician operations performed on a ticket.
    """
    __tablename__ = "ticket_labor"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    ticket_id = Column(String(36), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    service_catalog_item_id = Column(String(36), ForeignKey("service_catalog_items.id", ondelete="SET NULL"), nullable=True)

    name = Column(String(200), nullable=False)
    sac_code = Column(String(20), default="9987", nullable=False)
    labor_price = Column(Float, default=0.0, nullable=False)
    tax_rate = Column(Float, default=18.0, nullable=False)
    total_price = Column(Float, default=0.0, nullable=False)

    commission_rate = Column(Float, default=0.0, nullable=False)  # Commission % (e.g. 15.0)
    commission_amount = Column(Float, default=0.0, nullable=False)  # Calculated commission in INR
    assigned_tech_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    duration_minutes = Column(Integer, default=30, nullable=False)

    status = Column(String(20), default="pending", nullable=False)  # pending, in_progress, completed
    completed_at = Column(DateTime(timezone=True), nullable=True)

    ticket = relationship("Ticket", back_populates="labor_items")
    service_item = relationship("ServiceCatalogItem", foreign_keys=[service_catalog_item_id])
    assigned_tech = relationship("User", foreign_keys=[assigned_tech_id])


class TicketMedia(Base, TimestampMixin):
    """
    Pre/post inspection and diagnostic proof photos/videos.
    """
    __tablename__ = "ticket_media"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    ticket_id = Column(String(36), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)

    media_type = Column(String(30), default="before", nullable=False, index=True)  # before, after, diagnostic_proof
    file_url = Column(String(500), nullable=False)
    file_name = Column(String(200), nullable=True)
    file_size_kb = Column(Integer, default=0, nullable=False)
    notes = Column(Text, nullable=True)

    uploaded_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    ticket = relationship("Ticket", back_populates="media")
    uploaded_by = relationship("User", foreign_keys=[uploaded_by_id])


class TicketEstimate(Base, TimestampMixin):
    """
    Cost estimate with 1-click tokenized customer approval link.
    """
    __tablename__ = "ticket_estimates"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    ticket_id = Column(String(36), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    estimate_number = Column(String(50), nullable=False, index=True)

    # Secure token for 1-click approval via SMS / WhatsApp link
    approval_token = Column(String(64), unique=True, default=generate_tracking_token, nullable=False, index=True)
    approval_status = Column(String(20), default="pending", nullable=False, index=True)  # draft, pending, approved, rejected

    parts_subtotal = Column(Float, default=0.0, nullable=False)
    labor_subtotal = Column(Float, default=0.0, nullable=False)
    tax_total = Column(Float, default=0.0, nullable=False)
    grand_total = Column(Float, default=0.0, nullable=False)

    line_items = Column(JSON, default=list, nullable=False)  # Serialized snapshot of parts & labor
    customer_notes = Column(Text, nullable=True)

    approved_at = Column(DateTime(timezone=True), nullable=True)
    customer_ip = Column(String(50), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    ticket = relationship("Ticket", back_populates="estimates")


class TicketSubcontract(Base, TimestampMixin):
    """
    Subcontract external repairs (e.g. lathe work, BGA re-balling, engine machining).
    """
    __tablename__ = "ticket_subcontracts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    ticket_id = Column(String(36), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)

    vendor_name = Column(String(150), nullable=False)
    vendor_phone = Column(String(30), nullable=True)
    task_description = Column(Text, nullable=False)

    cost = Column(Float, default=0.0, nullable=False)  # What vendor charges us
    charged_to_customer = Column(Float, default=0.0, nullable=False)  # What we bill the client

    status = Column(String(30), default="dispatched", nullable=False, index=True)  # dispatched, in_progress, returned, cancelled
    dispatch_date = Column(DateTime(timezone=True), nullable=True)
    expected_return_date = Column(DateTime(timezone=True), nullable=True)
    actual_return_date = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    ticket = relationship("Ticket", back_populates="subcontracts")
