from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    JSON,
)
from sqlalchemy.orm import relationship
from app.models.base import Base, TimestampMixin, generate_uuid, utc_now


class NoticeBoardPost(Base, TimestampMixin):
    """
    Subcontracting bulletin, spare sourcing request, equipment exchange,
    or internal company notice published to the Ads/Tender board.
    """
    __tablename__ = "notice_board_posts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(
        String(36), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )  # None represents an Enterprise-wide Global broadcast
    author_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Categories: subcontracting, spare_sourcing, internal_notice, equipment_exchange, urgent_help
    category = Column(String(50), nullable=False, index=True, default="subcontracting")
    title = Column(String(250), nullable=False)
    description = Column(Text, nullable=False)

    # Urgency tier: low, normal, high, critical
    urgency = Column(String(20), nullable=False, default="normal", index=True)
    # Lifecycle: open, in_progress, closed, expired
    status = Column(String(20), nullable=False, default="open", index=True)

    # Optional commercial details
    budget_or_price = Column(Float, nullable=True)
    currency = Column(String(10), nullable=False, default="INR")
    part_number_or_sku = Column(String(100), nullable=True)
    device_model = Column(String(150), nullable=True)  # e.g., "LG Front Load DirectDrive Inverter"

    # Contact & deadline info
    contact_phone = Column(String(30), nullable=True)
    contact_email = Column(String(100), nullable=True)
    location_city = Column(String(100), nullable=True, default="Mumbai")
    expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Metadata & attachment links
    attachments = Column(JSON, default=list, nullable=False)  # List of URLs or image paths
    responses_count = Column(Integer, default=0, nullable=False)

    # Relationships
    branch = relationship("Branch", foreign_keys=[branch_id])
    author = relationship("User", foreign_keys=[author_id])
    responses = relationship(
        "NoticeResponse", back_populates="post", cascade="all, delete-orphan", order_by="desc(NoticeResponse.created_at)"
    )


class NoticeResponse(Base, TimestampMixin):
    """
    Bids, quotations, or collaborative responses submitted by technicians,
    managers, or partner workshops to a bulletin post.
    """
    __tablename__ = "notice_responses"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    post_id = Column(
        String(36), ForeignKey("notice_board_posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    responder_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    quote_amount = Column(Float, nullable=True)  # Proposed price or subcontracting charge
    message = Column(Text, nullable=False)
    estimated_delivery_days = Column(Integer, nullable=True)

    # Response status: pending, accepted, rejected
    status = Column(String(20), nullable=False, default="pending")

    # Relationships
    post = relationship("NoticeBoardPost", back_populates="responses")
    responder = relationship("User", foreign_keys=[responder_id])
