import secrets
from sqlalchemy import Boolean, Column, String, Float, Integer, Text, JSON, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.base import TimestampMixin, generate_uuid, utc_now


def generate_short_code() -> str:
    """Generate a clean 8-character token for short-link click tracking."""
    return secrets.token_urlsafe(6)


class NotificationTemplate(Base, TimestampMixin):
    """
    Notification message template with support for WhatsApp, SMS, and Email channels,
    including TRAI DLT registration identifiers for India compliance.
    """
    __tablename__ = "notification_templates"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=True, index=True)

    name = Column(String(100), nullable=False, index=True)  # e.g. ticket_intake, estimate_approval, ready_for_pickup
    channel = Column(String(20), default="whatsapp", nullable=False, index=True)  # whatsapp, sms, email
    category = Column(String(50), default="service_transactional", nullable=False, index=True)  # service_transactional, service_promotional, reminder, campaign

    # TRAI / DLT compliance identifiers for Indian SMS regulations
    dlt_template_id = Column(String(50), nullable=True, index=True)
    dlt_sender_id = Column(String(20), nullable=True)  # Header/Sender ID e.g. OMNISP

    subject = Column(String(255), nullable=True)  # For email
    body = Column(Text, nullable=False)  # Supports {{client_name}}, {{ticket_number}}, {{tracking_url}}, etc.
    variables = Column(JSON, default=list, nullable=False)  # List of variable placeholders

    is_active = Column(Boolean, default=True, nullable=False)

    branch = relationship("Branch", foreign_keys=[branch_id])
    logs = relationship("NotificationLog", back_populates="template", cascade="all, delete-orphan")


class NotificationOptOut(Base, TimestampMixin):
    """
    DLT / TRAI / NDNC National Do Not Call compliance opt-out registry.
    Before dispatching any marketing or reminder message, this registry is scrubbed.
    """
    __tablename__ = "notification_opt_outs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    phone = Column(String(30), nullable=False, index=True)
    email = Column(String(150), nullable=True, index=True)
    channel = Column(String(20), default="all", nullable=False)  # all, sms, whatsapp, email
    opt_out = Column(Boolean, default=True, nullable=False)
    reason = Column(String(255), nullable=True)
    source = Column(String(50), default="manual", nullable=False)  # manual, sms_keyword, unsubscribe_link, trai_dnd
    opted_out_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class NotificationLog(Base, TimestampMixin):
    """
    Immutable delivery audit log for every dispatched SMS, WhatsApp, and Email notification,
    including short-link click tracking.
    """
    __tablename__ = "notification_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True)
    ticket_id = Column(String(36), ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True, index=True)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)

    channel = Column(String(20), nullable=False, index=True)  # whatsapp, sms, email
    recipient_phone = Column(String(30), nullable=True, index=True)
    recipient_email = Column(String(150), nullable=True)

    template_id = Column(String(36), ForeignKey("notification_templates.id", ondelete="SET NULL"), nullable=True)
    template_name = Column(String(100), nullable=True)
    category = Column(String(50), default="transactional", nullable=False)

    dlt_template_id = Column(String(50), nullable=True)
    content = Column(Text, nullable=False)

    status = Column(String(20), default="queued", nullable=False, index=True)  # queued, sent, delivered, failed, read, opted_out
    vendor_message_id = Column(String(100), nullable=True)  # Provider ID (Twilio/Gupshup/WhatsApp)
    error_reason = Column(String(255), nullable=True)
    cost = Column(Float, default=0.0, nullable=False)

    # Click tracking
    click_token = Column(String(32), unique=True, default=generate_short_code, nullable=False, index=True)
    click_target_url = Column(String(500), nullable=True)
    clicked_at = Column(DateTime(timezone=True), nullable=True)
    click_count = Column(Integer, default=0, nullable=False)
    user_agent = Column(String(255), nullable=True)
    ip_address = Column(String(50), nullable=True)

    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    branch = relationship("Branch", foreign_keys=[branch_id])
    ticket = relationship("Ticket", foreign_keys=[ticket_id])
    client = relationship("Client", foreign_keys=[client_id])
    template = relationship("NotificationTemplate", back_populates="logs")
