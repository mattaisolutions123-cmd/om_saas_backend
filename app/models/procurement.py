from sqlalchemy import Column, String, Float, Integer, Boolean, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.models.base import TimestampMixin, generate_uuid, utc_now
from app.db.session import Base


class PurchaseOrder(Base, TimestampMixin):
    """
    Purchase Order issued to a supplier for replenishment or special customer order.
    Lifecycle: Draft -> Approved -> Ordered -> Partial -> Completed -> Cancelled
    """
    __tablename__ = "purchase_orders"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    supplier_id = Column(String(36), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False)

    po_number = Column(String(50), unique=True, index=True, nullable=False)  # e.g. PO-2026-0001
    status = Column(String(30), nullable=False, default="Draft")  # Draft, Approved, Ordered, Partial, Completed, Cancelled

    order_date = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    expected_delivery_date = Column(DateTime(timezone=True), nullable=True)

    subtotal = Column(Float, nullable=False, default=0.0)
    tax_total = Column(Float, nullable=False, default=0.0)
    grand_total = Column(Float, nullable=False, default=0.0)

    notes = Column(Text, nullable=True)

    created_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    branch = relationship("Branch")
    supplier = relationship("Supplier", backref="purchase_orders")
    created_by = relationship("User", foreign_keys=[created_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    items = relationship("PurchaseOrderItem", back_populates="purchase_order", cascade="all, delete-orphan")
    grns = relationship("GoodsReceivedNote", back_populates="purchase_order")


class PurchaseOrderItem(Base):
    """
    Line item on a Purchase Order.
    """
    __tablename__ = "purchase_order_items"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    purchase_order_id = Column(String(36), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False)
    inventory_item_id = Column(String(36), ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False)

    quantity_ordered = Column(Float, nullable=False, default=1.0)
    quantity_received = Column(Float, nullable=False, default=0.0)
    unit_cost = Column(Float, nullable=False, default=0.0)
    tax_rate = Column(Float, nullable=False, default=18.0)
    tax_amount = Column(Float, nullable=False, default=0.0)
    total_amount = Column(Float, nullable=False, default=0.0)

    purchase_order = relationship("PurchaseOrder", back_populates="items")
    item = relationship("InventoryItem")


class GoodsReceivedNote(Base, TimestampMixin):
    """
    Goods Received Note (GRN) recording physical warehouse inbound intake,
    inspection, batch numbers, damages, and vendor invoice linking.
    """
    __tablename__ = "goods_received_notes"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    branch_id = Column(String(36), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    purchase_order_id = Column(String(36), ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True)
    supplier_id = Column(String(36), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False)

    grn_number = Column(String(50), unique=True, index=True, nullable=False)  # e.g. GRN-2026-0001
    status = Column(String(30), nullable=False, default="Completed")  # Draft, Inspected, Completed

    received_date = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    vendor_invoice_no = Column(String(100), nullable=True)
    vendor_invoice_date = Column(DateTime(timezone=True), nullable=True)
    vendor_invoice_amount = Column(Float, nullable=False, default=0.0)

    # 3-Way Match Verification Status: MATCHED, QUANTITY_MISMATCH, PRICE_MISMATCH, PENDING
    match_status = Column(String(30), nullable=False, default="MATCHED")
    match_notes = Column(Text, nullable=True)

    notes = Column(Text, nullable=True)
    received_by_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    branch = relationship("Branch")
    purchase_order = relationship("PurchaseOrder", back_populates="grns")
    supplier = relationship("Supplier")
    received_by = relationship("User")
    items = relationship("GRNItem", back_populates="grn", cascade="all, delete-orphan")


class GRNItem(Base):
    """
    Inbound line item on a GRN with damage/acceptance audit and batch tracking.
    """
    __tablename__ = "grn_items"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    grn_id = Column(String(36), ForeignKey("goods_received_notes.id", ondelete="CASCADE"), nullable=False)
    po_item_id = Column(String(36), ForeignKey("purchase_order_items.id", ondelete="SET NULL"), nullable=True)
    inventory_item_id = Column(String(36), ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False)
    warehouse_location_id = Column(String(36), ForeignKey("warehouse_locations.id", ondelete="SET NULL"), nullable=True)

    quantity_received = Column(Float, nullable=False, default=0.0)
    quantity_accepted = Column(Float, nullable=False, default=0.0)
    quantity_damaged = Column(Float, nullable=False, default=0.0)

    batch_number = Column(String(100), nullable=True)
    expiry_date = Column(DateTime(timezone=True), nullable=True)
    unit_cost = Column(Float, nullable=False, default=0.0)
    notes = Column(Text, nullable=True)

    grn = relationship("GoodsReceivedNote", back_populates="items")
    po_item = relationship("PurchaseOrderItem")
    item = relationship("InventoryItem")
    warehouse_location = relationship("WarehouseLocation")
