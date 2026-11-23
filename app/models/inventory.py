from sqlalchemy import Column, String, Float, Integer, Boolean, Text, ForeignKey, JSON, DateTime
from sqlalchemy.orm import relationship
from app.models.base import TimestampMixin, generate_uuid, utc_now
from app.db.session import Base


class WarehouseLocation(Base, TimestampMixin):
    """
    Physical storage location within a branch (e.g. Rack A-1, Bin 04, Shelf 2).
    """
    __tablename__ = "warehouse_locations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(100), nullable=False)
    code = Column(String(50), nullable=False)
    is_default = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)

    branch = relationship("Branch", backref="warehouse_locations")


class InventoryItem(Base, TimestampMixin):
    """
    Physical spare part, component, device, or retail merchandise item.
    """
    __tablename__ = "inventory_items"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=True)

    name = Column(String(200), nullable=False)
    sku = Column(String(100), unique=True, index=True, nullable=False)
    barcode = Column(String(100), unique=True, index=True, nullable=False)
    brand = Column(String(100), nullable=True)
    model_compatibility = Column(JSON, nullable=False, default=list)  # ["iPhone 13", "iPhone 14"]
    category = Column(String(100), nullable=False, default="General Spare Parts")
    unit = Column(String(20), nullable=False, default="PCS")  # PCS, MTR, KG, SET, LTR
    hsn_code = Column(String(20), nullable=False, default="8504")  # Indian Harmonized System of Nomenclature

    cost_price = Column(Float, nullable=False, default=0.0)  # Valuation/acquisition cost
    retail_price = Column(Float, nullable=False, default=0.0)  # MRP / Customer price
    wholesale_price = Column(Float, nullable=False, default=0.0)  # B2B / Technician price
    min_stock_level = Column(Float, nullable=False, default=5.0)  # Low stock reorder trigger
    max_stock_level = Column(Float, nullable=False, default=100.0)
    tax_rate = Column(Float, nullable=False, default=18.0)  # GST rate: 0, 5, 12, 18, 28

    costing_method = Column(String(20), nullable=False, default="FIFO")  # FIFO, WAC
    track_inventory = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True)

    branch = relationship("Branch", backref="inventory_items")
    stock_ledgers = relationship("StockLedger", back_populates="item", cascade="all, delete-orphan")


class StockLedger(Base):
    """
    Double-entry immutable stock movement record.
    """
    __tablename__ = "stock_ledgers"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    inventory_item_id = Column(String(36), ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False)
    warehouse_location_id = Column(String(36), ForeignKey("warehouse_locations.id", ondelete="SET NULL"), nullable=True)

    movement_type = Column(String(50), nullable=False)  # PURCHASE_GRN, SALE_POS, WORK_ORDER_USED, TRANSFER_OUT, TRANSFER_IN, WRITE_OFF, STOCKTAKE_ADJUSTMENT, RETURN
    quantity_change = Column(Float, nullable=False)  # e.g. +10.0 or -2.0
    running_balance = Column(Float, nullable=False)  # Stock on hand after this transaction
    unit_cost = Column(Float, nullable=False, default=0.0)
    total_cost = Column(Float, nullable=False, default=0.0)

    reference_type = Column(String(50), nullable=True)  # PO, GRN, TICKET, INVOICE, TRANSFER, STOCKTAKE, SCRAP
    reference_id = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)

    created_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    item = relationship("InventoryItem", back_populates="stock_ledgers")
    warehouse_location = relationship("WarehouseLocation")
    created_by = relationship("User")


class StockReservation(Base, TimestampMixin):
    """
    Temporary or diagnostic allocation of stock (e.g. parts held for a scheduled repair ticket or POS checkout).
    """
    __tablename__ = "stock_reservations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    inventory_item_id = Column(String(36), ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False)

    quantity = Column(Float, nullable=False, default=1.0)
    reserved_for_type = Column(String(50), nullable=False)  # ticket, pos_cart, transfer
    reserved_for_id = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False, default="active")  # active, consumed, released
    expires_at = Column(DateTime(timezone=True), nullable=True)

    item = relationship("InventoryItem")
