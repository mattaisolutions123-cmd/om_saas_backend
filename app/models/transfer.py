from sqlalchemy import Column, String, Float, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.models.base import TimestampMixin, generate_uuid, utc_now
from app.db.session import Base


class BranchStockTransfer(Base, TimestampMixin):
    """
    Inter-branch stock transfer movement.
    Lifecycle: requested -> in-transit -> received -> cancelled
    """
    __tablename__ = "branch_stock_transfers"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    transfer_number = Column(String(50), unique=True, index=True, nullable=False)  # e.g. TR-2026-0001

    source_branch_id = Column(String(36), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)
    destination_branch_id = Column(String(36), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)

    status = Column(String(30), nullable=False, default="requested")  # requested, in-transit, received, cancelled

    requested_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    shipped_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    received_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    shipped_at = Column(DateTime(timezone=True), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=True)

    carrier_name = Column(String(100), nullable=True)
    tracking_reference = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)

    source_branch = relationship("Branch", foreign_keys=[source_branch_id])
    destination_branch = relationship("Branch", foreign_keys=[destination_branch_id])
    requested_by = relationship("User", foreign_keys=[requested_by_id])
    shipped_by = relationship("User", foreign_keys=[shipped_by_id])
    received_by = relationship("User", foreign_keys=[received_by_id])
    items = relationship("BranchStockTransferItem", back_populates="transfer", cascade="all, delete-orphan")


class BranchStockTransferItem(Base):
    """
    Line item for inter-branch transfer.
    """
    __tablename__ = "branch_stock_transfer_items"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    transfer_id = Column(String(36), ForeignKey("branch_stock_transfers.id", ondelete="CASCADE"), nullable=False)
    inventory_item_id = Column(String(36), ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False)

    quantity_requested = Column(Float, nullable=False, default=1.0)
    quantity_sent = Column(Float, nullable=False, default=0.0)
    quantity_received = Column(Float, nullable=False, default=0.0)

    transfer = relationship("BranchStockTransfer", back_populates="items")
    item = relationship("InventoryItem")
