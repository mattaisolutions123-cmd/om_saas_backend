from sqlalchemy import Boolean, Column, String, Integer, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.base import TimestampMixin, generate_uuid


class CustomFieldDefinition(Base, TimestampMixin):
    __tablename__ = "custom_field_definitions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=True, index=True)

    # Target entity: ticket, client, inventory, supplier, task
    entity = Column(String(50), nullable=False, index=True)

    # Machine key & display name
    field_key = Column(String(100), nullable=False, index=True)
    name = Column(String(150), nullable=False)

    # 12 types: short_text, long_text, number, dropdown, multi_select, date_time,
    # currency, checkbox, image_upload, signature_pad, barcode_scan, formula
    field_type = Column(String(50), nullable=False)

    # Validation & Behavior rules
    required = Column(Boolean, default=False, nullable=False)
    unique = Column(Boolean, default=False, nullable=False)
    placeholder = Column(String(255), nullable=True)
    default_value = Column(JSON, nullable=True)

    # Options for dropdown / multi_select: list of {"label": "...", "value": "..."}
    options = Column(JSON, default=list, nullable=False)

    # Formula configuration: {"expression": "...", "depends_on": [...]}
    formula_expression = Column(JSON, nullable=True)

    # Role-based visibility and conditional display
    # role_visibility: list of role slugs, e.g. ["owner", "branch_manager", "technician"] (empty means all)
    role_visibility = Column(JSON, default=list, nullable=False)

    # conditional_display: {"field": "...", "operator": "eq|neq|in|gt|lt", "value": ...}
    conditional_display = Column(JSON, nullable=True)

    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    branch = relationship("Branch", foreign_keys=[branch_id])
