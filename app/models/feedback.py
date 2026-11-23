from sqlalchemy import Column, String, Integer, Text, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.base import TimestampMixin, generate_uuid, utc_now


class CustomerFeedback(Base, TimestampMixin):
    """
    Customer feedback survey submitted after ticket delivery.
    """
    __tablename__ = "customer_feedback"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    ticket_id = Column(String(36), ForeignKey("tickets.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)

    # 1 to 5 Stars
    overall_rating = Column(Integer, nullable=False)  # 1 to 5
    technician_rating = Column(Integer, default=5, nullable=False)  # 1 to 5
    nps_score = Column(Integer, default=10, nullable=False)  # Net Promoter Score 0 to 10

    # Categorical satisfaction ratings
    turnaround_satisfaction = Column(String(30), default="on_time", nullable=False)  # very_fast, on_time, delayed
    pricing_satisfaction = Column(String(30), default="fair", nullable=False)  # good_value, fair, expensive

    comments = Column(Text, nullable=True)
    recommend_to_others = Column(Boolean, default=True, nullable=False)
    customer_ip = Column(String(50), nullable=True)
    submitted_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    ticket = relationship("Ticket", foreign_keys=[ticket_id])
    client = relationship("Client", foreign_keys=[client_id])
    branch = relationship("Branch", foreign_keys=[branch_id])
