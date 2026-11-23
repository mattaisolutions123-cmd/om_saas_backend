from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# 1. Warehouse Location
class WarehouseLocationBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    code: str = Field(..., min_length=1, max_length=50)
    is_default: bool = False
    is_active: bool = True


class WarehouseLocationCreate(WarehouseLocationBase):
    branch_id: str


class WarehouseLocationResponse(WarehouseLocationBase):
    id: str
    branch_id: str
    created_at: datetime

    class Config:
        from_attributes = True


# 2. Inventory Item
class InventoryItemBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    sku: str = Field(..., min_length=1, max_length=100)
    barcode: str = Field(..., min_length=1, max_length=100)
    brand: Optional[str] = None
    model_compatibility: List[str] = Field(default_factory=list)
    category: str = Field(default="General Spare Parts", max_length=100)
    unit: str = Field(default="PCS", max_length=20)
    hsn_code: str = Field(default="8504", max_length=20)
    cost_price: float = Field(default=0.0, ge=0.0)
    retail_price: float = Field(default=0.0, ge=0.0)
    wholesale_price: float = Field(default=0.0, ge=0.0)
    min_stock_level: float = Field(default=5.0, ge=0.0)
    max_stock_level: float = Field(default=100.0, ge=0.0)
    tax_rate: float = Field(default=18.0, ge=0.0)
    costing_method: str = Field(default="FIFO", pattern="^(FIFO|WAC)$")
    track_inventory: bool = True
    is_active: bool = True


class InventoryItemCreate(InventoryItemBase):
    branch_id: Optional[str] = None
    initial_stock: Optional[float] = Field(default=0.0, ge=0.0)
    warehouse_location_id: Optional[str] = None


class InventoryItemUpdate(BaseModel):
    name: Optional[str] = None
    brand: Optional[str] = None
    model_compatibility: Optional[List[str]] = None
    category: Optional[str] = None
    unit: Optional[str] = None
    hsn_code: Optional[str] = None
    cost_price: Optional[float] = None
    retail_price: Optional[float] = None
    wholesale_price: Optional[float] = None
    min_stock_level: Optional[float] = None
    max_stock_level: Optional[float] = None
    tax_rate: Optional[float] = None
    costing_method: Optional[str] = None
    track_inventory: Optional[bool] = None
    is_active: Optional[bool] = None


class InventoryItemResponse(InventoryItemBase):
    id: str
    branch_id: Optional[str] = None
    current_stock: float = 0.0
    allocated_stock: float = 0.0
    available_stock: float = 0.0
    stock_status: str = "IN_STOCK"  # IN_STOCK, LOW_STOCK, OUT_OF_STOCK
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InventoryItemListResponse(BaseModel):
    items: List[InventoryItemResponse]
    total: int


# 3. Stock Movement & Ledger
class StockMovementCreate(BaseModel):
    inventory_item_id: str
    movement_type: str = Field(..., pattern="^(PURCHASE_GRN|SALE_POS|WORK_ORDER_USED|TRANSFER_OUT|TRANSFER_IN|WRITE_OFF|STOCKTAKE_ADJUSTMENT|RETURN)$")
    quantity_change: float
    unit_cost: float = Field(default=0.0, ge=0.0)
    warehouse_location_id: Optional[str] = None
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    notes: Optional[str] = None


class StockLedgerResponse(BaseModel):
    id: str
    branch_id: str
    inventory_item_id: str
    warehouse_location_id: Optional[str] = None
    movement_type: str
    quantity_change: float
    running_balance: float
    unit_cost: float
    total_cost: float
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    notes: Optional[str] = None
    created_by_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# 4. Low Stock Alert
class LowStockAlertResponse(BaseModel):
    item_id: str
    item_name: str
    sku: str
    barcode: str
    category: str
    unit: str
    current_stock: float
    min_stock_level: float
    shortfall: float
    cost_price: float
    estimated_reorder_cost: float
