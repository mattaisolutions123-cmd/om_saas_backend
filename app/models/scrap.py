from sqlalchemy import Column, String, Float, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.models.base import TimestampMixin, generate_uuid, utc_now
from app.db.session import Base


class ScrapWriteOff(Base):
    """
    Scrap, obsolescence, damage, or theft inventory write-off voucher.
    """
    __tablename__ = "scrap_write_offs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    inventory_item_id = Column(String(36), ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False)
    warehouse_location_id = Column(String(36), ForeignKey("warehouse_locations.id", ondelete="SET NULL"), nullable=True)

    voucher_number = Column(String(50), unique=True, index=True, nullable=False)  # e.g. SCRAP-2026-0001
    quantity = Column(Float, nullable=False)
    unit_cost = Column(Float, nullable=False, default=0.0)
    total_cost = Column(Float, nullable=False, default=0.0)

    # Standard reason codes:
    # damaged_in_transit, expired, defective_supplier, lost_theft, demo_sample, internal_use
    reason_code = Column(String(50), nullable=False)
    notes = Column(Text, nullable=True)

    created_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    branch = relationship("Branch")
    item = relationship("InventoryItem")
    warehouse_location = relationship("WarehouseLocation")
    created_by = relationship("User", foreign_keys=[created_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])
