from sqlalchemy import Boolean, Column, String, Float, Text, JSON, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.base import TimestampMixin, generate_uuid, utc_now


class Client(Base, TimestampMixin):
    __tablename__ = "clients"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=True, index=True)

    # Type: individual vs corporate
    client_type = Column(String(20), default="individual", nullable=False, index=True)

    # Primary Contact & Identity
    name = Column(String(200), nullable=False, index=True)
    phone = Column(String(30), nullable=False, index=True)
    email = Column(String(100), nullable=True, index=True)

    # Multiple Contacts: [{"name": "...", "phone": "...", "email": "...", "designation": "..."}]
    contacts = Column(JSON, default=list, nullable=False)

    # Multiple Billing Addresses: [{"label": "Head Office", "address_line": "...", "city": "...", "state": "...", "state_code": "27", "pincode": "...", "gstin": "...", "is_default": True}]
    billing_addresses = Column(JSON, default=list, nullable=False)

    # Indian GST details
    gstin = Column(String(25), nullable=True, index=True)
    pan = Column(String(20), nullable=True)

    # Credit & Commercial Terms
    credit_limit = Column(Float, default=0.0, nullable=False)
    credit_period_days = Column(Float, default=0, nullable=False)  # 0, 15, 30, 45, 60, 90
    discount_terms = Column(JSON, default=dict, nullable=False)  # {"discount_percent": 5.0, "notes": "..."}

    # Annual Maintenance Contract (AMC)
    # {"has_amc": True, "plan_name": "Comprehensive Annual Care", "start_date": "2026-01-01", "end_date": "2026-12-31", "sla_hours": 4}
    amc = Column(JSON, default=dict, nullable=False)

    # Behavioral & Classification Tags: ["VIP", "difficult", "prompt_payer", "wholesale", "corporate"]
    tags = Column(JSON, default=list, nullable=False)

    # Customer Messaging Opt-Ins: {"sms": True, "whatsapp": True, "email": True, "promotional": False}
    messaging_opt_in = Column(JSON, default=lambda: {"sms": True, "whatsapp": True, "email": True, "promotional": True}, nullable=False)

    # Internal Notes & General Observations
    notes = Column(Text, nullable=True)

    # Dynamic JSONB Custom Fields (compatible with Phase 1 CustomFieldDefinition for entity="client")
    custom_fields = Column(JSON, default=dict, nullable=False)

    # Financial Cached Aggregates (updated reactively on invoices/payments)
    total_spent = Column(Float, default=0.0, nullable=False)
    outstanding_balance = Column(Float, default=0.0, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    branch = relationship("Branch", foreign_keys=[branch_id])
    assets = relationship("Asset", back_populates="client", cascade="all, delete-orphan", order_by="Asset.created_at.desc()")
    interactions = relationship("ClientInteraction", back_populates="client", cascade="all, delete-orphan", order_by="ClientInteraction.created_at.desc()")
