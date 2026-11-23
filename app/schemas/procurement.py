from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# 1. Purchase Order
class PurchaseOrderItemBase(BaseModel):
    inventory_item_id: str
    quantity_ordered: float = Field(..., gt=0.0)
    unit_cost: float = Field(..., ge=0.0)
    tax_rate: float = Field(default=18.0, ge=0.0)


class PurchaseOrderItemCreate(PurchaseOrderItemBase):
    pass


class PurchaseOrderItemResponse(PurchaseOrderItemBase):
    id: str
    purchase_order_id: str
    quantity_received: float = 0.0
    tax_amount: float
    total_amount: float
    item_name: Optional[str] = None
    item_sku: Optional[str] = None
    item_barcode: Optional[str] = None

    class Config:
        from_attributes = True


class PurchaseOrderCreate(BaseModel):
    branch_id: Optional[str] = None
    supplier_id: str
    expected_delivery_date: Optional[datetime] = None
    notes: Optional[str] = None
    items: List[PurchaseOrderItemCreate] = Field(..., min_length=1)


class PurchaseOrderUpdate(BaseModel):
    status: Optional[str] = None  # Draft, Approved, Ordered, Partial, Completed, Cancelled
    expected_delivery_date: Optional[datetime] = None
    notes: Optional[str] = None


class PurchaseOrderResponse(BaseModel):
    id: str
    branch_id: str
    supplier_id: str
    supplier_name: Optional[str] = None
    po_number: str
    status: str
    order_date: datetime
    expected_delivery_date: Optional[datetime] = None
    subtotal: float
    tax_total: float
    grand_total: float
    notes: Optional[str] = None
    created_by_id: Optional[str] = None
    approved_by_id: Optional[str] = None
    approved_at: Optional[datetime] = None
    items: List[PurchaseOrderItemResponse] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PurchaseOrderListResponse(BaseModel):
    items: List[PurchaseOrderResponse]
    total: int


# 2. Goods Received Note (GRN)
class GRNItemCreate(BaseModel):
    inventory_item_id: str
    po_item_id: Optional[str] = None
    warehouse_location_id: Optional[str] = None
    quantity_received: float = Field(..., ge=0.0)
    quantity_accepted: float = Field(..., ge=0.0)
    quantity_damaged: float = Field(default=0.0, ge=0.0)
    batch_number: Optional[str] = None
    expiry_date: Optional[datetime] = None
    unit_cost: float = Field(default=0.0, ge=0.0)
    notes: Optional[str] = None


class GRNItemResponse(BaseModel):
    id: str
    grn_id: str
    po_item_id: Optional[str] = None
    inventory_item_id: str
    item_name: Optional[str] = None
    item_sku: Optional[str] = None
    warehouse_location_id: Optional[str] = None
    warehouse_location_name: Optional[str] = None
    quantity_received: float
    quantity_accepted: float
    quantity_damaged: float
    batch_number: Optional[str] = None
    expiry_date: Optional[datetime] = None
    unit_cost: float
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class GoodsReceivedNoteCreate(BaseModel):
    branch_id: Optional[str] = None
    purchase_order_id: Optional[str] = None
    supplier_id: str
    vendor_invoice_no: Optional[str] = None
    vendor_invoice_date: Optional[datetime] = None
    vendor_invoice_amount: float = Field(default=0.0, ge=0.0)
    notes: Optional[str] = None
    items: List[GRNItemCreate] = Field(..., min_length=1)


class GoodsReceivedNoteResponse(BaseModel):
    id: str
    branch_id: str
    purchase_order_id: Optional[str] = None
    po_number: Optional[str] = None
    supplier_id: str
    supplier_name: Optional[str] = None
    grn_number: str
    status: str
    received_date: datetime
    vendor_invoice_no: Optional[str] = None
    vendor_invoice_date: Optional[datetime] = None
    vendor_invoice_amount: float
    match_status: str
    match_notes: Optional[str] = None
    notes: Optional[str] = None
    received_by_id: Optional[str] = None
    items: List[GRNItemResponse] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# 3. Three-Way Match (PO vs GRN vs Vendor Invoice)
class ThreeWayMatchLine(BaseModel):
    item_id: str
    item_name: str
    sku: str
    po_quantity: float
    po_unit_cost: float
    po_total: float
    grn_accepted_quantity: float
    grn_damaged_quantity: float
    invoice_unit_cost: float
    invoice_total: float
    quantity_variance: float
    price_variance: float
    match_status: str  # MATCHED, QUANTITY_MISMATCH, PRICE_MISMATCH


class ThreeWayMatchResponse(BaseModel):
    po_id: Optional[str] = None
    po_number: Optional[str] = None
    grn_id: str
    grn_number: str
    supplier_id: str
    supplier_name: str
    vendor_invoice_no: Optional[str] = None
    vendor_invoice_amount: float
    po_grand_total: float
    grn_received_value: float
    total_variance_amount: float
    overall_match_status: str  # MATCHED, QUANTITY_MISMATCH, PRICE_MISMATCH, UNMATCHED
    match_lines: List[ThreeWayMatchLine]


# 4. Branch Stock Transfer
class BranchStockTransferItemCreate(BaseModel):
    inventory_item_id: str
    quantity_requested: float = Field(..., gt=0.0)


class BranchStockTransferItemResponse(BaseModel):
    id: str
    transfer_id: str
    inventory_item_id: str
    item_name: Optional[str] = None
    item_sku: Optional[str] = None
    quantity_requested: float
    quantity_sent: float
    quantity_received: float

    class Config:
        from_attributes = True


class BranchStockTransferCreate(BaseModel):
    source_branch_id: str
    destination_branch_id: str
    carrier_name: Optional[str] = None
    tracking_reference: Optional[str] = None
    notes: Optional[str] = None
    items: List[BranchStockTransferItemCreate] = Field(..., min_length=1)


class BranchStockTransferResponse(BaseModel):
    id: str
    transfer_number: str
    source_branch_id: str
    source_branch_name: Optional[str] = None
    destination_branch_id: str
    destination_branch_name: Optional[str] = None
    status: str  # requested, in-transit, received, cancelled
    carrier_name: Optional[str] = None
    tracking_reference: Optional[str] = None
    notes: Optional[str] = None
    shipped_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    items: List[BranchStockTransferItemResponse] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# 5. Scrap Write-Off
class ScrapWriteOffCreate(BaseModel):
    branch_id: Optional[str] = None
    inventory_item_id: str
    warehouse_location_id: Optional[str] = None
    quantity: float = Field(..., gt=0.0)
    reason_code: str = Field(..., pattern="^(damaged_in_transit|expired|defective_supplier|lost_theft|demo_sample|internal_use)$")
    notes: Optional[str] = None


class ScrapWriteOffResponse(BaseModel):
    id: str
    branch_id: str
    voucher_number: str
    inventory_item_id: str
    item_name: Optional[str] = None
    item_sku: Optional[str] = None
    warehouse_location_id: Optional[str] = None
    warehouse_location_name: Optional[str] = None
    quantity: float
    unit_cost: float
    total_cost: float
    reason_code: str
    notes: Optional[str] = None
    created_by_id: Optional[str] = None
    approved_by_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# 6. Stocktaking Audit
class StocktakingCountScan(BaseModel):
    inventory_item_id: str
    warehouse_location_id: Optional[str] = None
    counted_quantity: float = Field(..., ge=0.0)
    manager_notes: Optional[str] = None


class StocktakingItemResponse(BaseModel):
    id: str
    stocktaking_audit_id: str
    inventory_item_id: str
    item_name: Optional[str] = None
    item_sku: Optional[str] = None
    item_barcode: Optional[str] = None
    warehouse_location_id: Optional[str] = None
    warehouse_location_name: Optional[str] = None
    expected_quantity: float
    counted_quantity: float
    variance: float
    unit_cost: float
    variance_cost: float
    manager_notes: Optional[str] = None
    adjustment_status: str

    class Config:
        from_attributes = True


class StocktakingAuditCreate(BaseModel):
    branch_id: Optional[str] = None
    audit_type: str = Field(default="blind_count", pattern="^(blind_count|standard)$")
    notes: Optional[str] = None


class StocktakingAuditResponse(BaseModel):
    id: str
    branch_id: str
    audit_number: str
    audit_type: str
    status: str  # in_progress, review, completed, cancelled
    notes: Optional[str] = None
    conducted_by_id: Optional[str] = None
    reviewed_by_id: Optional[str] = None
    completed_at: Optional[datetime] = None
    items: List[StocktakingItemResponse] = []
    total_expected_qty: float = 0.0
    total_counted_qty: float = 0.0
    total_variance_qty: float = 0.0
    total_variance_value: float = 0.0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
