from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from app.db.session import get_db
from app.models.inventory import InventoryItem, WarehouseLocation, StockLedger
from app.schemas.inventory import (
    WarehouseLocationCreate,
    WarehouseLocationResponse,
    InventoryItemCreate,
    InventoryItemUpdate,
    InventoryItemResponse,
    InventoryItemListResponse,
    StockMovementCreate,
    StockLedgerResponse,
    LowStockAlertResponse,
)
from app.services.inventory_service import InventoryService
from app.services.audit import log_audit_event

router = APIRouter(prefix="/inventory", tags=["Inventory & Warehouse"])


# 1. Warehouse Locations
@router.get("/locations", response_model=List[WarehouseLocationResponse])
async def list_warehouse_locations(
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(WarehouseLocation).where(WarehouseLocation.is_active == True)
    if branch_id:
        query = query.where(WarehouseLocation.branch_id == branch_id)
    items = (await db.execute(query.order_by(WarehouseLocation.name.asc()))).scalars().all()
    return items


@router.post("/locations", response_model=WarehouseLocationResponse, status_code=status.HTTP_201_CREATED)
async def create_warehouse_location(
    payload: WarehouseLocationCreate,
    db: AsyncSession = Depends(get_db),
):
    loc = WarehouseLocation(
        branch_id=payload.branch_id,
        name=payload.name.strip(),
        code=payload.code.strip().upper(),
        is_default=payload.is_default,
        is_active=payload.is_active,
    )
    db.add(loc)
    await db.commit()
    await db.refresh(loc)
    return loc


# 2. Inventory Items
@router.get("", response_model=InventoryItemListResponse)
@router.get("/items", response_model=InventoryItemListResponse)
async def list_inventory_items(
    search: Optional[str] = Query(None, description="Search by SKU, barcode, name, brand"),
    category: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    stock_status: Optional[str] = Query(None, pattern="^(IN_STOCK|LOW_STOCK|OUT_OF_STOCK)$"),
    branch_id: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(InventoryItem)
    if is_active is not None:
        query = query.where(InventoryItem.is_active == is_active)
    if category:
        query = query.where(InventoryItem.category == category)
    if brand:
        query = query.where(InventoryItem.brand == brand)
    if branch_id:
        query = query.where(or_(InventoryItem.branch_id == branch_id, InventoryItem.branch_id == None))
    if search:
        search_fmt = f"%{search.strip()}%"
        query = query.where(
            or_(
                InventoryItem.name.ilike(search_fmt),
                InventoryItem.sku.ilike(search_fmt),
                InventoryItem.barcode.ilike(search_fmt),
                InventoryItem.brand.ilike(search_fmt),
            )
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(InventoryItem.name.asc()).offset(skip).limit(limit)
    items = (await db.execute(query)).scalars().all()

    # Calculate stock levels dynamically for each item
    response_items = []
    for item in items:
        stock_on_hand = await InventoryService.get_current_stock(db, item.id, branch_id)
        allocated = await InventoryService.get_allocated_stock(db, item.id, branch_id)
        available = max(0.0, stock_on_hand - allocated)

        status_val = "IN_STOCK"
        if stock_on_hand <= 0:
            status_val = "OUT_OF_STOCK"
        elif stock_on_hand <= item.min_stock_level:
            status_val = "LOW_STOCK"

        if stock_status and status_val != stock_status:
            continue

        resp_item = InventoryItemResponse(
            id=item.id,
            branch_id=item.branch_id,
            name=item.name,
            sku=item.sku,
            barcode=item.barcode,
            brand=item.brand,
            model_compatibility=item.model_compatibility or [],
            category=item.category,
            unit=item.unit,
            hsn_code=item.hsn_code,
            cost_price=item.cost_price,
            retail_price=item.retail_price,
            wholesale_price=item.wholesale_price,
            min_stock_level=item.min_stock_level,
            max_stock_level=item.max_stock_level,
            tax_rate=item.tax_rate,
            costing_method=item.costing_method,
            track_inventory=item.track_inventory,
            is_active=item.is_active,
            current_stock=stock_on_hand,
            allocated_stock=allocated,
            available_stock=available,
            stock_status=status_val,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        response_items.append(resp_item)

    return InventoryItemListResponse(items=response_items, total=total)


@router.post("", response_model=InventoryItemResponse, status_code=status.HTTP_201_CREATED)
async def create_inventory_item(
    payload: InventoryItemCreate,
    db: AsyncSession = Depends(get_db),
):
    # Check uniqueness of SKU and Barcode
    existing = await db.execute(
        select(InventoryItem).where(
            or_(
                InventoryItem.sku == payload.sku.strip().upper(),
                InventoryItem.barcode == payload.barcode.strip(),
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="An inventory item with this SKU or Barcode already exists",
        )

    item = InventoryItem(
        branch_id=payload.branch_id,
        name=payload.name.strip(),
        sku=payload.sku.strip().upper(),
        barcode=payload.barcode.strip(),
        brand=payload.brand.strip() if payload.brand else None,
        model_compatibility=payload.model_compatibility or [],
        category=payload.category.strip(),
        unit=payload.unit.strip().upper(),
        hsn_code=payload.hsn_code.strip(),
        cost_price=payload.cost_price,
        retail_price=payload.retail_price,
        wholesale_price=payload.wholesale_price,
        min_stock_level=payload.min_stock_level,
        max_stock_level=payload.max_stock_level,
        tax_rate=payload.tax_rate,
        costing_method=payload.costing_method,
        track_inventory=payload.track_inventory,
        is_active=payload.is_active,
    )
    db.add(item)
    await db.flush()

    # Record initial stock if provided
    initial_stock = payload.initial_stock or 0.0
    if initial_stock > 0 and payload.branch_id:
        await InventoryService.record_stock_movement(
            session=db,
            branch_id=payload.branch_id,
            inventory_item_id=item.id,
            movement_type="PURCHASE_GRN",
            quantity_change=initial_stock,
            unit_cost=payload.cost_price,
            warehouse_location_id=payload.warehouse_location_id,
            reference_type="OPENING_STOCK",
            notes="Opening stock balance on item creation",
        )

    await db.commit()
    await db.refresh(item)

    await log_audit_event(
        db=db,
        action="CREATE",
        entity="inventory_item",
        entity_id=item.id,
        after_state={"sku": item.sku, "name": item.name, "retail_price": item.retail_price},
    )

    stock_on_hand = await InventoryService.get_current_stock(db, item.id, item.branch_id)
    return InventoryItemResponse(
        id=item.id,
        branch_id=item.branch_id,
        name=item.name,
        sku=item.sku,
        barcode=item.barcode,
        brand=item.brand,
        model_compatibility=item.model_compatibility or [],
        category=item.category,
        unit=item.unit,
        hsn_code=item.hsn_code,
        cost_price=item.cost_price,
        retail_price=item.retail_price,
        wholesale_price=item.wholesale_price,
        min_stock_level=item.min_stock_level,
        max_stock_level=item.max_stock_level,
        tax_rate=item.tax_rate,
        costing_method=item.costing_method,
        track_inventory=item.track_inventory,
        is_active=item.is_active,
        current_stock=stock_on_hand,
        allocated_stock=0.0,
        available_stock=stock_on_hand,
        stock_status="IN_STOCK" if stock_on_hand > 0 else "OUT_OF_STOCK",
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/lookup", response_model=InventoryItemResponse)
async def lookup_by_code(
    code: str = Query(..., description="Barcode or SKU to scan"),
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(InventoryItem).where(
        or_(
            InventoryItem.barcode == code.strip(),
            InventoryItem.sku == code.strip().upper(),
        )
    )
    res = await db.execute(query)
    item = res.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="No inventory item found matching barcode/SKU")

    stock_on_hand = await InventoryService.get_current_stock(db, item.id, branch_id)
    allocated = await InventoryService.get_allocated_stock(db, item.id, branch_id)
    available = max(0.0, stock_on_hand - allocated)

    status_val = "IN_STOCK"
    if stock_on_hand <= 0:
        status_val = "OUT_OF_STOCK"
    elif stock_on_hand <= item.min_stock_level:
        status_val = "LOW_STOCK"

    return InventoryItemResponse(
        id=item.id,
        branch_id=item.branch_id,
        name=item.name,
        sku=item.sku,
        barcode=item.barcode,
        brand=item.brand,
        model_compatibility=item.model_compatibility or [],
        category=item.category,
        unit=item.unit,
        hsn_code=item.hsn_code,
        cost_price=item.cost_price,
        retail_price=item.retail_price,
        wholesale_price=item.wholesale_price,
        min_stock_level=item.min_stock_level,
        max_stock_level=item.max_stock_level,
        tax_rate=item.tax_rate,
        costing_method=item.costing_method,
        track_inventory=item.track_inventory,
        is_active=item.is_active,
        current_stock=stock_on_hand,
        allocated_stock=allocated,
        available_stock=available,
        stock_status=status_val,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/low-stock", response_model=List[LowStockAlertResponse])
async def list_low_stock_alerts(
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Query items that are below or at their min_stock_level threshold.
    """
    items_res = await db.execute(
        select(InventoryItem).where(
            and_(
                InventoryItem.is_active == True,
                InventoryItem.track_inventory == True,
            )
        )
    )
    items = items_res.scalars().all()

    alerts: List[LowStockAlertResponse] = []
    for item in items:
        stock = await InventoryService.get_current_stock(db, item.id, branch_id)
        if stock <= item.min_stock_level:
            shortfall = max(0.0, item.min_stock_level - stock)
            alerts.append(
                LowStockAlertResponse(
                    item_id=item.id,
                    item_name=item.name,
                    sku=item.sku,
                    barcode=item.barcode,
                    category=item.category,
                    unit=item.unit,
                    current_stock=stock,
                    min_stock_level=item.min_stock_level,
                    shortfall=shortfall,
                    cost_price=item.cost_price,
                    estimated_reorder_cost=round(shortfall * item.cost_price, 2),
                )
            )

    return sorted(alerts, key=lambda a: a.shortfall, reverse=True)


@router.get("/{id}", response_model=InventoryItemResponse)
async def get_inventory_item(
    id: str,
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(InventoryItem).where(InventoryItem.id == id))
    item = res.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    stock_on_hand = await InventoryService.get_current_stock(db, item.id, branch_id)
    allocated = await InventoryService.get_allocated_stock(db, item.id, branch_id)
    available = max(0.0, stock_on_hand - allocated)

    status_val = "IN_STOCK"
    if stock_on_hand <= 0:
        status_val = "OUT_OF_STOCK"
    elif stock_on_hand <= item.min_stock_level:
        status_val = "LOW_STOCK"

    return InventoryItemResponse(
        id=item.id,
        branch_id=item.branch_id,
        name=item.name,
        sku=item.sku,
        barcode=item.barcode,
        brand=item.brand,
        model_compatibility=item.model_compatibility or [],
        category=item.category,
        unit=item.unit,
        hsn_code=item.hsn_code,
        cost_price=item.cost_price,
        retail_price=item.retail_price,
        wholesale_price=item.wholesale_price,
        min_stock_level=item.min_stock_level,
        max_stock_level=item.max_stock_level,
        tax_rate=item.tax_rate,
        costing_method=item.costing_method,
        track_inventory=item.track_inventory,
        is_active=item.is_active,
        current_stock=stock_on_hand,
        allocated_stock=allocated,
        available_stock=available,
        stock_status=status_val,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.put("/{id}", response_model=InventoryItemResponse)
async def update_inventory_item(
    id: str,
    payload: InventoryItemUpdate,
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(InventoryItem).where(InventoryItem.id == id))
    item = res.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    old_vals = {"name": item.name, "retail_price": item.retail_price}
    update_data = payload.dict(exclude_unset=True)
    for field, val in update_data.items():
        setattr(item, field, val)

    await db.commit()
    await db.refresh(item)

    stock_on_hand = await InventoryService.get_current_stock(db, item.id, item.branch_id)
    return InventoryItemResponse(
        id=item.id,
        branch_id=item.branch_id,
        name=item.name,
        sku=item.sku,
        barcode=item.barcode,
        brand=item.brand,
        model_compatibility=item.model_compatibility or [],
        category=item.category,
        unit=item.unit,
        hsn_code=item.hsn_code,
        cost_price=item.cost_price,
        retail_price=item.retail_price,
        wholesale_price=item.wholesale_price,
        min_stock_level=item.min_stock_level,
        max_stock_level=item.max_stock_level,
        tax_rate=item.tax_rate,
        costing_method=item.costing_method,
        track_inventory=item.track_inventory,
        is_active=item.is_active,
        current_stock=stock_on_hand,
        allocated_stock=0.0,
        available_stock=stock_on_hand,
        stock_status="IN_STOCK" if stock_on_hand > 0 else "OUT_OF_STOCK",
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/{id}/ledger", response_model=List[StockLedgerResponse])
async def get_item_stock_ledger(
    id: str,
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(StockLedger)
        .where(StockLedger.inventory_item_id == id)
        .order_by(StockLedger.created_at.desc())
        .limit(limit)
    )
    records = (await db.execute(query)).scalars().all()
    return records
