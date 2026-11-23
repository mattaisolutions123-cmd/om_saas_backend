from sqlalchemy import Column, String, Float, Text, JSON, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.base import TimestampMixin, generate_uuid, utc_now


class PaymentTransaction(Base, TimestampMixin):
    """
    Online payment initiation record (UPI Intent / QR code, Cards, Netbanking).
    """
    __tablename__ = "payment_transactions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    ticket_id = Column(String(36), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)

    amount = Column(Float, nullable=False)
    payment_method = Column(String(30), default="upi", nullable=False)  # upi, qr, card, netbanking
    
    # UPI Specific details
    upi_vpa = Column(String(100), default="omnisuite@icici", nullable=False)
    upi_intent_url = Column(Text, nullable=False)  # upi://pay?pa=...&pn=...&am=...&tn=...&tr=...
    transaction_ref = Column(String(64), unique=True, nullable=False, index=True)  # TXN-202611-XXXXX

    gateway_order_id = Column(String(100), nullable=True)
    gateway_payment_id = Column(String(100), nullable=True)

    status = Column(String(20), default="initiated", nullable=False, index=True)  # initiated, pending, success, failed, expired
    payer_vpa = Column(String(100), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(JSON, default=dict, nullable=False)

    ticket = relationship("Ticket", foreign_keys=[ticket_id])
    branch = relationship("Branch", foreign_keys=[branch_id])
    client = relationship("Client", foreign_keys=[client_id])
