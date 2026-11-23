from sqlalchemy import Boolean, Column, String, Text, JSON, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.base import TimestampMixin, generate_uuid, utc_now


class ScheduledReport(Base, TimestampMixin):
    """
    Automated recurring report dispatch schedule (Email delivery of PDF, Excel, or CSV).
    """
    __tablename__ = "scheduled_reports"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=True, index=True)
    created_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    report_type = Column(String(50), nullable=False, index=True)  # income_expense, order_profit, stock_valuation, etc.
    title = Column(String(150), nullable=False)
    frequency = Column(String(20), default="weekly", nullable=False)  # daily, weekly, monthly
    export_format = Column(String(20), default="pdf", nullable=False)  # pdf, excel, csv

    recipients = Column(JSON, default=list, nullable=False)  # List of email addresses: ["director@omnisuite.in"]
    filters = Column(JSON, default=dict, nullable=False)  # e.g. {"branch_id": "...", "category": "..."}

    is_active = Column(Boolean, default=True, nullable=False)
    last_sent_at = Column(DateTime(timezone=True), nullable=True)

    branch = relationship("Branch", foreign_keys=[branch_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
