from sqlalchemy import Boolean, Column, String, Float, Integer, Text, JSON, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.base import TimestampMixin, generate_uuid, utc_now


class AutomationRule(Base, TimestampMixin):
    """
    Automated notification trigger rule:
    1. Feedback survey 24h after delivery
    2. Maintenance reminder after 6 months
    3. Warranty-expiry notice 15 days prior
    4. Seasonal campaigns to segments
    """
    __tablename__ = "automation_rules"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=True, index=True)

    name = Column(String(100), nullable=False)
    code = Column(String(50), unique=True, nullable=False, index=True)  # FEEDBACK_24H, MAINTENANCE_6M, WARRANTY_15D, SEASONAL_PROMO
    trigger_event = Column(String(50), nullable=False)  # ticket_delivered, ticket_closed, warranty_expiring_soon, seasonal_schedule

    # Timing parameters
    delay_hours = Column(Integer, default=0, nullable=False)
    delay_days = Column(Integer, default=0, nullable=False)
    advance_days = Column(Integer, default=0, nullable=False)  # For lookahead triggers (e.g. 15 days prior to warranty expiration)

    channel = Column(String(20), default="whatsapp", nullable=False)  # whatsapp, sms, email
    template_name = Column(String(100), nullable=False)
    conditions = Column(JSON, default=dict, nullable=False)  # Optional filtering criteria

    is_active = Column(Boolean, default=True, nullable=False)
    execution_count = Column(Integer, default=0, nullable=False)
    last_run_at = Column(DateTime(timezone=True), nullable=True)

    branch = relationship("Branch", foreign_keys=[branch_id])
    jobs = relationship("ScheduledJob", back_populates="rule", cascade="all, delete-orphan")


class ScheduledJob(Base, TimestampMixin):
    """
    Instance of an automation task waiting to be executed at scheduled_for.
    """
    __tablename__ = "scheduled_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    rule_id = Column(String(36), ForeignKey("automation_rules.id", ondelete="CASCADE"), nullable=True, index=True)
    ticket_id = Column(String(36), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=True, index=True)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id = Column(String(36), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True, index=True)

    job_type = Column(String(50), nullable=False, index=True)  # feedback_survey_24h, maintenance_reminder_6m, warranty_expiry_15d, campaign_blast
    scheduled_for = Column(DateTime(timezone=True), nullable=False, index=True)

    status = Column(String(20), default="scheduled", nullable=False, index=True)  # scheduled, processing, completed, skipped_opt_out, failed
    executed_at = Column(DateTime(timezone=True), nullable=True)
    execution_result = Column(JSON, default=dict, nullable=False)

    rule = relationship("AutomationRule", back_populates="jobs")
    ticket = relationship("Ticket", foreign_keys=[ticket_id])
    client = relationship("Client", foreign_keys=[client_id])
    asset = relationship("Asset", foreign_keys=[asset_id])


class MarketingCampaign(Base, TimestampMixin):
    """
    Promotional / seasonal campaign dispatched to targeted audience segments.
    """
    __tablename__ = "marketing_campaigns"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=True, index=True)

    name = Column(String(150), nullable=False)
    channel = Column(String(20), default="whatsapp", nullable=False)  # whatsapp, sms, email
    segment_type = Column(String(50), default="all", nullable=False)  # all, high_value, inactive_90d, warranty_expired, brand_specific, pin_code_cluster
    segment_criteria = Column(JSON, default=dict, nullable=False)  # e.g. {"min_spend": 10000, "days_inactive": 90, "brand": "Crompton"}

    template_id = Column(String(36), ForeignKey("notification_templates.id", ondelete="SET NULL"), nullable=True)
    custom_message = Column(Text, nullable=True)

    status = Column(String(20), default="draft", nullable=False, index=True)  # draft, scheduled, in_progress, completed, cancelled
    scheduled_at = Column(DateTime(timezone=True), nullable=True)

    sent_count = Column(Integer, default=0, nullable=False)
    delivered_count = Column(Integer, default=0, nullable=False)
    failed_count = Column(Integer, default=0, nullable=False)
    clicked_count = Column(Integer, default=0, nullable=False)
    opt_out_count = Column(Integer, default=0, nullable=False)

    branch = relationship("Branch", foreign_keys=[branch_id])
    template = relationship("NotificationTemplate", foreign_keys=[template_id])
