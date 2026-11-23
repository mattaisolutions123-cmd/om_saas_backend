from sqlalchemy import Boolean, Column, String, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.base import TimestampMixin, generate_uuid


class DocumentTemplate(Base, TimestampMixin):
    __tablename__ = "document_templates"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=True, index=True)

    # invoice, receipt, job_sheet, barcode_label, delivery_challan, estimate
    type = Column(String(50), nullable=False, index=True)
    name = Column(String(150), nullable=False)

    # 58mm (thermal POS), 80mm (wide thermal), A4 (laser/sheet)
    paper_width = Column(String(20), default="80mm", nullable=False)

    # HTML body supporting mustache/jinja tokens: {{company_name}}, {{customer_name}}, {{items}}, etc.
    html_body = Column(Text, nullable=False)

    # List of variable tokens e.g. ["ticket_number", "customer_name", "items", "total_amount", "balance"]
    variables = Column(JSON, default=list, nullable=False)

    is_default = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    branch = relationship("Branch", foreign_keys=[branch_id])
