from sqlalchemy import Column, String, Float, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.models.base import TimestampMixin, generate_uuid, utc_now
from app.db.session import Base


class StocktakingAudit(Base, TimestampMixin):
    """
    Physical stocktake session (blind count or standard count), variance calculation, and adjustment.
    """
    __tablename__ = "stocktaking_audits"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)

    audit_number = Column(String(50), unique=True, index=True, nullable=False)  # e.g. STK-2026-0001
    audit_type = Column(String(30), nullable=False, default="blind_count")  # blind_count, standard
    status = Column(String(30), nullable=False, default="in_progress")  # in_progress, review, completed, cancelled

    notes = Column(Text, nullable=True)

    conducted_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    branch = relationship("Branch")
    conducted_by = relationship("User", foreign_keys=[conducted_by_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])
    items = relationship("StocktakingItem", back_populates="audit", cascade="all, delete-orphan")


class StocktakingItem(Base):
    """
    Line item for stocktaking with expected vs counted comparison.
    """
    __tablename__ = "stocktaking_items"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    stocktaking_audit_id = Column(String(36), ForeignKey("stocktaking_audits.id", ondelete="CASCADE"), nullable=False)
    inventory_item_id = Column(String(36), ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False)
    warehouse_location_id = Column(String(36), ForeignKey("warehouse_locations.id", ondelete="SET NULL"), nullable=True)

    expected_quantity = Column(Float, nullable=False, default=0.0)  # System record at freeze time
    counted_quantity = Column(Float, nullable=False, default=0.0)   # Physical scan count
    variance = Column(Float, nullable=False, default=0.0)           # counted - expected
    unit_cost = Column(Float, nullable=False, default=0.0)
    variance_cost = Column(Float, nullable=False, default=0.0)      # variance * unit_cost

    manager_notes = Column(Text, nullable=True)
    adjustment_status = Column(String(20), nullable=False, default="pending")  # pending, adjusted, rejected

    audit = relationship("StocktakingAudit", back_populates="items")
    item = relationship("InventoryItem")
    warehouse_location = relationship("WarehouseLocation")
