from sqlalchemy import Column, String, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.base import TimestampMixin, generate_uuid, utc_now


class ClientInteraction(Base, TimestampMixin):
    __tablename__ = "client_interactions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=True, index=True)

    actor_id = Column(String(36), nullable=True)
    actor_name = Column(String(150), default="System", nullable=False)
    actor_role = Column(String(50), nullable=True)

    # Interaction Type: call, sms, whatsapp, email, visit, note, status_change, payment, amc
    type = Column(String(50), default="note", nullable=False, index=True)

    # Direction: inbound, outbound, internal
    direction = Column(String(20), default="internal", nullable=False)

    title = Column(String(200), nullable=False)
    details = Column(Text, nullable=True)

    # Metadata: {"ticket_id": "...", "amount": 1500.0, "call_duration_sec": 140, "sms_status": "delivered"}
    extra_metadata = Column(JSON, default=dict, nullable=False)

    # Relationships
    client = relationship("Client", back_populates="interactions")
    branch = relationship("Branch", foreign_keys=[branch_id])
