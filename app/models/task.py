import secrets
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, String, Float, Integer, Text, JSON, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.base import TimestampMixin, generate_uuid, utc_now


class Task(Base, TimestampMixin):
    """
    Core OmniSuite Task Entity.
    Supports manual tasks, auto-generated tasks from ticket status changes,
    and SLA-warning tasks. Enforces author vs executor segregation,
    category classification, deadline tracking, canonical status lifecycle
    (Backlog -> In Progress -> Review -> Done), priority tiers,
    and SLA escalation indicators.
    """
    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    task_number = Column(String(50), unique=True, index=True, nullable=False)  # e.g. TSK-202611-0001
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Origin: manual, auto-from-ticket-status, SLA-warning
    task_type = Column(String(50), default="manual", nullable=False, index=True)

    # Segregation: Author vs Executor
    author_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    executor_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # Category: Workshop, Procurement, Customer Communication, Lathe, Delivery, Inspection, SLA Alert, General
    category = Column(String(50), default="General", nullable=False, index=True)

    # Status: Backlog -> In Progress -> Review -> Done (or Cancelled)
    status = Column(String(30), default="Backlog", nullable=False, index=True)

    # Priority: low, standard, high, urgent
    priority = Column(String(20), default="standard", nullable=False, index=True)

    # SLA Tier Config & Escalation
    sla_tier = Column(String(20), nullable=True, index=True)  # T1, T2, T3
    deadline = Column(DateTime(timezone=True), nullable=True, index=True)
    sla_deadline = Column(DateTime(timezone=True), nullable=True)
    
    # SLA Status: OK, WARNING_75, L1_PUSH, L2_BREACHED, L3_WHATSAPP_SENT, L4_ANALYTICS_LOGGED
    sla_status = Column(String(30), default="OK", nullable=False, index=True)
    is_urgent = Column(Boolean, default=False, nullable=False, index=True)
    is_expired = Column(Boolean, default=False, nullable=False, index=True)
    overdue_minutes = Column(Integer, default=0, nullable=False)

    # Pin-code for geographic clustering and delivery/planner routing
    pin_code = Column(String(20), nullable=True, index=True)

    # Optional Link to Core Work Order Ticket & Client
    ticket_id = Column(String(36), ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True, index=True)

    # Checklist & Tags
    checklist = Column(JSON, default=list, nullable=False)  # [{"id": "1", "text": "...", "completed": false}]
    tags = Column(JSON, default=list, nullable=False)        # ["lathe", "urgent", "pickup"]

    # Resolution & Metadata
    completed_at = Column(DateTime(timezone=True), nullable=True)
    task_metadata = Column(JSON, default=dict, nullable=False)  # {"trigger_rule": "...", "reassign_history": [...]}

    # Relationships
    branch = relationship("Branch", foreign_keys=[branch_id])
    author = relationship("User", foreign_keys=[author_id])
    executor = relationship("User", foreign_keys=[executor_id])
    ticket = relationship("Ticket", foreign_keys=[ticket_id])
    escalation_logs = relationship("EscalationLog", back_populates="task", cascade="all, delete-orphan")


class SLATierConfig(Base, TimestampMixin):
    """
    SLA Tier Configuration.
    - T1 Emergency: < 4h
    - T2 High: < 24h with assign + diagnose within 2h
    - T3 Standard: 3-7 days (72h - 168h)
    """
    __tablename__ = "sla_tier_configs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=True, index=True)

    tier_code = Column(String(20), nullable=False, index=True)  # T1, T2, T3
    name = Column(String(100), nullable=False)                 # "T1 Emergency (<4h)"
    resolution_hours = Column(Float, nullable=False)           # 4.0, 24.0, 72.0
    diagnosis_hours = Column(Float, default=2.0, nullable=False)  # Milestone: assign+diagnose within 2h for T2
    warning_threshold_percent = Column(Float, default=75.0, nullable=False)  # 75% elapsed
    l1_amber_hours_before = Column(Float, default=4.0, nullable=False)       # T-4h push amber
    tech_penalty_points = Column(Float, default=10.0, nullable=False)        # Tech score penalty upon L2 breach
    customer_whatsapp_template = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    branch = relationship("Branch", foreign_keys=[branch_id])


class EscalationLog(Base, TimestampMixin):
    """
    Audit log of SLA triggers and escalation events:
    - 75% Elapsed (urgent flag + high priority)
    - L1 (T-4h push warning, amber state)
    - L2 Breach (EXPIRED, overdue counter, manager alert, 1-click reassign, penalty points)
    - L3 Customer Courtesy WhatsApp message
    - L4 Monthly on-time % analytics calculation
    """
    __tablename__ = "escalation_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    task_id = Column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True, index=True)
    ticket_id = Column(String(36), ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True, index=True)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)

    # Level: 75%_ELAPSED, L1_PUSH, L2_BREACH, L3_WHATSAPP, L4_ANALYTICS
    escalation_level = Column(String(30), nullable=False, index=True)
    severity = Column(String(20), default="amber", nullable=False)  # amber, red, critical, info
    message = Column(Text, nullable=False)

    # Responsible technician & penalty
    tech_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    penalty_applied = Column(Float, default=0.0, nullable=False)

    # Manager review & action
    acknowledged_by_manager = Column(Boolean, default=False, nullable=False)
    acknowledged_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)

    # WhatsApp courtesy payload (for L3)
    whatsapp_payload = Column(JSON, default=dict, nullable=False)

    # Relationships
    task = relationship("Task", back_populates="escalation_logs")
    ticket = relationship("Ticket", foreign_keys=[ticket_id])
    branch = relationship("Branch", foreign_keys=[branch_id])
    tech = relationship("User", foreign_keys=[tech_id])
    acknowledged_by = relationship("User", foreign_keys=[acknowledged_by_id])


class StatusTriggerRule(Base, TimestampMixin):
    """
    Status-Trigger Rules:
    - Lathe Work -> "Deliver core to lathe workshop"
    - Spare Wait -> "Source part"
    - Work Done -> "Notify client for pickup"
    """
    __tablename__ = "status_trigger_rules"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=True, index=True)

    ticket_status_source = Column(String(50), nullable=False, index=True)  # "Lathe Work", "Spare Wait", "Work Done"
    task_title_template = Column(String(255), nullable=False)
    task_category = Column(String(50), nullable=False)                     # "Workshop", "Procurement", "Customer Communication"
    priority = Column(String(20), default="high", nullable=False)
    due_hours = Column(Float, default=24.0, nullable=False)
    role_target = Column(String(50), default="technician", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    branch = relationship("Branch", foreign_keys=[branch_id])
