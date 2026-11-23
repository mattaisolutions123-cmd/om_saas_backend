from sqlalchemy import Boolean, Column, String, Integer, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from app.db.session import Base
from app.models.base import TimestampMixin, generate_uuid


class Handbook(Base, TimestampMixin):
    __tablename__ = "handbooks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=True, index=True)

    # e.g., brands_models, defect_codes, units, payment_tags, expense_categories
    code = Column(String(100), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)

    is_hierarchical = Column(Boolean, default=False, nullable=False)
    is_system = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    branch = relationship("Branch", foreign_keys=[branch_id])
    items = relationship(
        "HandbookItem",
        back_populates="handbook",
        cascade="all, delete-orphan",
        order_by="HandbookItem.sort_order",
    )


class HandbookItem(Base, TimestampMixin):
    __tablename__ = "handbook_items"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    handbook_id = Column(String(36), ForeignKey("handbooks.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = Column(String(36), ForeignKey("handbook_items.id", ondelete="CASCADE"), nullable=True, index=True)

    code = Column(String(100), nullable=False, index=True)
    name = Column(String(200), nullable=False)

    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Extra data for multi-language labels, rates, metadata:
    # {"labels": {"hi": "...", "mr": "..."}, "rate": 18.0, "icon": "...", "badge_color": "..."}
    extra_data = Column(JSON, default=dict, nullable=False)

    # Relationships
    handbook = relationship("Handbook", back_populates="items")
    parent = relationship("HandbookItem", remote_side=[id], back_populates="children")
    children = relationship("HandbookItem", back_populates="parent", cascade="all, delete-orphan")
