from sqlalchemy import Boolean, Column, String, Integer, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.base import TimestampMixin, generate_uuid


class StatusPipeline(Base, TimestampMixin):
    __tablename__ = "status_pipelines"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=True, index=True)

    entity = Column(String(50), default="ticket", nullable=False, index=True)  # ticket, task
    name = Column(String(150), nullable=False)
    code = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)

    is_default = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    branch = relationship("Branch", foreign_keys=[branch_id])
    statuses = relationship("StatusDefinition", back_populates="pipeline", cascade="all, delete-orphan", order_by="StatusDefinition.sort_order")
    transitions = relationship("StatusTransition", back_populates="pipeline", cascade="all, delete-orphan")


class StatusDefinition(Base, TimestampMixin):
    __tablename__ = "status_definitions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    pipeline_id = Column(String(36), ForeignKey("status_pipelines.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(100), nullable=False)
    code = Column(String(100), nullable=False, index=True)

    bg_color = Column(String(30), default="#f1f5f9", nullable=False)
    text_color = Column(String(30), default="#0f172a", nullable=False)
    icon = Column(String(50), default="circle", nullable=False)

    sort_order = Column(Integer, default=0, nullable=False)
    is_initial = Column(Boolean, default=False, nullable=False)
    is_terminal = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    pipeline = relationship("StatusPipeline", back_populates="statuses")
    incoming_transitions = relationship("StatusTransition", foreign_keys="StatusTransition.to_status_id", back_populates="to_status")
    outgoing_transitions = relationship("StatusTransition", foreign_keys="StatusTransition.from_status_id", back_populates="from_status")


class StatusTransition(Base, TimestampMixin):
    __tablename__ = "status_transitions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    pipeline_id = Column(String(36), ForeignKey("status_pipelines.id", ondelete="CASCADE"), nullable=False, index=True)

    from_status_id = Column(String(36), ForeignKey("status_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    to_status_id = Column(String(36), ForeignKey("status_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=True)

    # Guards: {"closure_gate": True, "required_fields": [...], "allowed_roles": [...]}
    # Closure gate blocks transition unless balance == 0 or manager override is active
    guards = Column(JSON, default=dict, nullable=False)

    # Event hooks: {"send_sms": {"enabled": True, "template": "..."}, "lock_fields": [...], "auto_create_task": {...}}
    event_hooks = Column(JSON, default=dict, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    pipeline = relationship("StatusPipeline", back_populates="transitions")
    from_status = relationship("StatusDefinition", foreign_keys=[from_status_id], back_populates="outgoing_transitions")
    to_status = relationship("StatusDefinition", foreign_keys=[to_status_id], back_populates="incoming_transitions")
