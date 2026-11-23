import uuid
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from app.db.session import get_db
from app.models.procurement import (
    PurchaseOrder,
    PurchaseOrderItem,
    GoodsReceivedNote,
    GRNItem,
)
from app.models.inventory import InventoryItem, WarehouseLocation
from app.models.supplier import Supplier
from app.models.transfer import BranchStockTransfer, BranchStockTransferItem
from app.models.scrap import ScrapWriteOff
from app.models.stocktaking import StocktakingAudit, StocktakingItem
from app.schemas.procurement import (
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
    PurchaseOrderResponse,
    PurchaseOrderItemResponse,
    PurchaseOrderListResponse,
    GoodsReceivedNoteCreate,
    GoodsReceivedNoteResponse,
    GRNItemResponse,
    ThreeWayMatchResponse,
    BranchStockTransferCreate,
    BranchStockTransferResponse,
    BranchStockTransferItemResponse,
    ScrapWriteOffCreate,
    ScrapWriteOffResponse,
    StocktakingAuditCreate,
    StocktakingAuditResponse,
    StocktakingItemResponse,
    StocktakingCountScan,
)
from app.services.inventory_service import InventoryService
from app.services.audit import log_audit_event

router = APIRouter(prefix="/procurement", tags=["Procurement & Supply Chain"])


# 1. Purchase Orders
@router.get("/purchase-orders", response_model=PurchaseOrderListResponse)
async def list_purchase_orders(
    status_filter: Optional[str] = Query(None, alias="status"),
    supplier_id: Optional[str] = Query(None),
    branch_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(PurchaseOrder)
    if status_filter:
        query = query.where(PurchaseOrder.status == status_filter)
    if supplier_id:
        query = query.where(PurchaseOrder.supplier_id == supplier_id)
    if branch_id:
        query = query.where(PurchaseOrder.branch_id == branch_id)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(PurchaseOrder.order_date.desc()).offset(skip).limit(limit)
    orders = (await db.execute(query)).scalars().all()

    resp_list = []
    for po in orders:
        # Load supplier
        supp = (await db.execute(select(Supplier).where(Supplier.id == po.supplier_id))).scalar_one_or_none()
        # Load lines
        lines = (await db.execute(select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == po.id))).scalars().all()
        line_resps = []
        for line in lines:
            inv = (await db.execute(select(InventoryItem).where(InventoryItem.id == line.inventory_item_id))).scalar_one_or_none()
            line_resps.append(
                PurchaseOrderItemResponse(
                    id=line.id,
                    purchase_order_id=line.purchase_order_id,
                    inventory_item_id=line.inventory_item_id,
                    quantity_ordered=line.quantity_ordered,
                    quantity_received=line.quantity_received,
                    unit_cost=line.unit_cost,
                    tax_rate=line.tax_rate,
                    tax_amount=line.tax_amount,
                    total_amount=line.total_amount,
                    item_name=inv.name if inv else None,
                    item_sku=inv.sku if inv else None,
                    item_barcode=inv.barcode if inv else None,
                )
            )

        resp_list.append(
            PurchaseOrderResponse(
                id=po.id,
                branch_id=po.branch_id,
                supplier_id=po.supplier_id,
                supplier_name=supp.name if supp else "Unknown",
                po_number=po.po_number,
                status=po.status,
                order_date=po.order_date,
                expected_delivery_date=po.expected_delivery_date,
                subtotal=po.subtotal,
                tax_total=po.tax_total,
                grand_total=po.grand_total,
                notes=po.notes,
                created_by_id=po.created_by_id,
                approved_by_id=po.approved_by_id,
                approved_at=po.approved_at,
                items=line_resps,
                created_at=po.created_at,
                updated_at=po.updated_at,
            )
        )

    return PurchaseOrderListResponse(items=resp_list, total=total)


@router.post("/purchase-orders", response_model=PurchaseOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_purchase_order(
    payload: PurchaseOrderCreate,
    db: AsyncSession = Depends(get_db),
):
    supplier = (await db.execute(select(Supplier).where(Supplier.id == payload.supplier_id))).scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    branch_id = payload.branch_id or supplier.branch_id
    if not branch_id:
        # Default to first branch
        from app.models.branch import Branch
        first_b = (await db.execute(select(Branch).limit(1))).scalar_one_or_none()
        branch_id = first_b.id if first_b else "DEFAULT"

    po_count = (await db.execute(select(func.count(PurchaseOrder.id)))).scalar() or 0
    po_number = f"PO-{datetime.now().strftime('%Y%m')}-{(po_count + 1):04d}"

    po = PurchaseOrder(
        branch_id=branch_id,
        supplier_id=payload.supplier_id,
        po_number=po_number,
        status="Draft",
        expected_delivery_date=payload.expected_delivery_date,
        notes=payload.notes,
        subtotal=0.0,
        tax_total=0.0,
        grand_total=0.0,
    )
    db.add(po)
    await db.flush()

    subtotal = 0.0
    tax_total = 0.0
    line_resps = []

    for item_in in payload.items:
        inv = (await db.execute(select(InventoryItem).where(InventoryItem.id == item_in.inventory_item_id))).scalar_one_or_none()
        if not inv:
            continue

        line_sub = item_in.quantity_ordered * item_in.unit_cost
        line_tax = round(line_sub * (item_in.tax_rate / 100.0), 2)
        line_total = line_sub + line_tax

        subtotal += line_sub
        tax_total += line_tax

        po_item = PurchaseOrderItem(
            purchase_order_id=po.id,
            inventory_item_id=item_in.inventory_item_id,
            quantity_ordered=item_in.quantity_ordered,
            quantity_received=0.0,
            unit_cost=item_in.unit_cost,
            tax_rate=item_in.tax_rate,
            tax_amount=line_tax,
            total_amount=line_total,
        )
        db.add(po_item)
        await db.flush()

        line_resps.append(
            PurchaseOrderItemResponse(
                id=po_item.id,
                purchase_order_id=po.id,
                inventory_item_id=inv.id,
                quantity_ordered=po_item.quantity_ordered,
                quantity_received=0.0,
                unit_cost=po_item.unit_cost,
                tax_rate=po_item.tax_rate,
                tax_amount=line_tax,
                total_amount=line_total,
                item_name=inv.name,
                item_sku=inv.sku,
                item_barcode=inv.barcode,
            )
        )

    po.subtotal = round(subtotal, 2)
    po.tax_total = round(tax_total, 2)
    po.grand_total = round(subtotal + tax_total, 2)

    await db.commit()
    await db.refresh(po)

    return PurchaseOrderResponse(
        id=po.id,
        branch_id=po.branch_id,
        supplier_id=po.supplier_id,
        supplier_name=supplier.name,
        po_number=po.po_number,
        status=po.status,
        order_date=po.order_date,
        expected_delivery_date=po.expected_delivery_date,
        subtotal=po.subtotal,
        tax_total=po.tax_total,
        grand_total=po.grand_total,
        notes=po.notes,
        created_by_id=po.created_by_id,
        approved_by_id=po.approved_by_id,
        approved_at=po.approved_at,
        items=line_resps,
        created_at=po.created_at,
        updated_at=po.updated_at,
    )


@router.put("/purchase-orders/{id}/approve", response_model=PurchaseOrderResponse)
async def approve_purchase_order(
    id: str,
    db: AsyncSession = Depends(get_db),
):
    po = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == id))).scalar_one_or_none()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    po.status = "Approved"
    po.approved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(po)

    supp = (await db.execute(select(Supplier).where(Supplier.id == po.supplier_id))).scalar_one_or_none()
    lines = (await db.execute(select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == po.id))).scalars().all()
    line_resps = []
    for line in lines:
        inv = (await db.execute(select(InventoryItem).where(InventoryItem.id == line.inventory_item_id))).scalar_one_or_none()
        line_resps.append(
            PurchaseOrderItemResponse(
                id=line.id,
                purchase_order_id=line.purchase_order_id,
                inventory_item_id=line.inventory_item_id,
                quantity_ordered=line.quantity_ordered,
                quantity_received=line.quantity_received,
                unit_cost=line.unit_cost,
                tax_rate=line.tax_rate,
                tax_amount=line.tax_amount,
                total_amount=line.total_amount,
                item_name=inv.name if inv else None,
                item_sku=inv.sku if inv else None,
                item_barcode=inv.barcode if inv else None,
            )
        )

    return PurchaseOrderResponse(
        id=po.id,
        branch_id=po.branch_id,
        supplier_id=po.supplier_id,
        supplier_name=supp.name if supp else "Unknown",
        po_number=po.po_number,
        status=po.status,
        order_date=po.order_date,
        expected_delivery_date=po.expected_delivery_date,
        subtotal=po.subtotal,
        tax_total=po.tax_total,
        grand_total=po.grand_total,
        notes=po.notes,
        created_by_id=po.created_by_id,
        approved_by_id=po.approved_by_id,
        approved_at=po.approved_at,
        items=line_resps,
        created_at=po.created_at,
        updated_at=po.updated_at,
    )


# 2. Goods Received Notes (GRN)
@router.get("/grns", response_model=List[GoodsReceivedNoteResponse])
async def list_grns(
    supplier_id: Optional[str] = Query(None),
    branch_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(GoodsReceivedNote)
    if supplier_id:
        query = query.where(GoodsReceivedNote.supplier_id == supplier_id)
    if branch_id:
        query = query.where(GoodsReceivedNote.branch_id == branch_id)

    query = query.order_by(GoodsReceivedNote.received_date.desc()).offset(skip).limit(limit)
    grns = (await db.execute(query)).scalars().all()

    resp_list = []
    for g in grns:
        supp = (await db.execute(select(Supplier).where(Supplier.id == g.supplier_id))).scalar_one_or_none()
        po = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == g.purchase_order_id))).scalar_one_or_none() if g.purchase_order_id else None

        lines = (await db.execute(select(GRNItem).where(GRNItem.grn_id == g.id))).scalars().all()
        line_resps = []
        for line in lines:
            inv = (await db.execute(select(InventoryItem).where(InventoryItem.id == line.inventory_item_id))).scalar_one_or_none()
            loc = (await db.execute(select(WarehouseLocation).where(WarehouseLocation.id == line.warehouse_location_id))).scalar_one_or_none() if line.warehouse_location_id else None
            line_resps.append(
                GRNItemResponse(
                    id=line.id,
                    grn_id=g.id,
                    po_item_id=line.po_item_id,
                    inventory_item_id=line.inventory_item_id,
                    item_name=inv.name if inv else None,
                    item_sku=inv.sku if inv else None,
                    warehouse_location_id=line.warehouse_location_id,
                    warehouse_location_name=loc.name if loc else None,
                    quantity_received=line.quantity_received,
                    quantity_accepted=line.quantity_accepted,
                    quantity_damaged=line.quantity_damaged,
                    batch_number=line.batch_number,
                    expiry_date=line.expiry_date,
                    unit_cost=line.unit_cost,
                    notes=line.notes,
                )
            )

        resp_list.append(
            GoodsReceivedNoteResponse(
                id=g.id,
                branch_id=g.branch_id,
                purchase_order_id=g.purchase_order_id,
                po_number=po.po_number if po else None,
                supplier_id=g.supplier_id,
                supplier_name=supp.name if supp else "Unknown",
                grn_number=g.grn_number,
                status=g.status,
                received_date=g.received_date,
                vendor_invoice_no=g.vendor_invoice_no,
                vendor_invoice_date=g.vendor_invoice_date,
                vendor_invoice_amount=g.vendor_invoice_amount,
                match_status=g.match_status,
                match_notes=g.match_notes,
                notes=g.notes,
                received_by_id=g.received_by_id,
                items=line_resps,
                created_at=g.created_at,
                updated_at=g.updated_at,
            )
        )
    return resp_list


@router.post("/grns", response_model=GoodsReceivedNoteResponse, status_code=status.HTTP_201_CREATED)
async def create_grn(
    payload: GoodsReceivedNoteCreate,
    db: AsyncSession = Depends(get_db),
):
    supplier = (await db.execute(select(Supplier).where(Supplier.id == payload.supplier_id))).scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    branch_id = payload.branch_id or supplier.branch_id
    if not branch_id:
        from app.models.branch import Branch
        first_b = (await db.execute(select(Branch).limit(1))).scalar_one_or_none()
        branch_id = first_b.id if first_b else "DEFAULT"

    grn_count = (await db.execute(select(func.count(GoodsReceivedNote.id)))).scalar() or 0
    grn_number = f"GRN-{datetime.now().strftime('%Y%m')}-{(grn_count + 1):04d}"

    grn = GoodsReceivedNote(
        branch_id=branch_id,
        purchase_order_id=payload.purchase_order_id,
        supplier_id=payload.supplier_id,
        grn_number=grn_number,
        status="Completed",
        vendor_invoice_no=payload.vendor_invoice_no,
        vendor_invoice_date=payload.vendor_invoice_date,
        vendor_invoice_amount=payload.vendor_invoice_amount,
        notes=payload.notes,
    )
    db.add(grn)
    await db.flush()

    line_resps = []
    all_po_items_completed = True

    for item_in in payload.items:
        inv = (await db.execute(select(InventoryItem).where(InventoryItem.id == item_in.inventory_item_id))).scalar_one_or_none()
        if not inv:
            continue

        grn_item = GRNItem(
            grn_id=grn.id,
            po_item_id=item_in.po_item_id,
            inventory_item_id=item_in.inventory_item_id,
            warehouse_location_id=item_in.warehouse_location_id,
            quantity_received=item_in.quantity_received,
            quantity_accepted=item_in.quantity_accepted,
            quantity_damaged=item_in.quantity_damaged,
            batch_number=item_in.batch_number,
            expiry_date=item_in.expiry_date,
            unit_cost=item_in.unit_cost,
            notes=item_in.notes,
        )
        db.add(grn_item)
        await db.flush()

        # Inbound Stock Ledger entry for accepted quantity
        if item_in.quantity_accepted > 0:
            await InventoryService.record_stock_movement(
                session=db,
                branch_id=branch_id,
                inventory_item_id=item_in.inventory_item_id,
                movement_type="PURCHASE_GRN",
                quantity_change=item_in.quantity_accepted,
                unit_cost=item_in.unit_cost,
                warehouse_location_id=item_in.warehouse_location_id,
                reference_type="GRN",
                reference_id=grn.grn_number,
                notes=f"Inbound intake via {grn.grn_number}. Batch: {item_in.batch_number or 'N/A'}",
            )

        # Update PO Item received quantity if linked
        if item_in.po_item_id:
            po_line = (await db.execute(select(PurchaseOrderItem).where(PurchaseOrderItem.id == item_in.po_item_id))).scalar_one_or_none()
            if po_line:
                po_line.quantity_received += item_in.quantity_accepted
                if po_line.quantity_received < po_line.quantity_ordered:
                    all_po_items_completed = False

        loc_name = None
        if item_in.warehouse_location_id:
            loc = (await db.execute(select(WarehouseLocation).where(WarehouseLocation.id == item_in.warehouse_location_id))).scalar_one_or_none()
            loc_name = loc.name if loc else None

        line_resps.append(
            GRNItemResponse(
                id=grn_item.id,
                grn_id=grn.id,
                po_item_id=item_in.po_item_id,
                inventory_item_id=inv.id,
                item_name=inv.name,
                item_sku=inv.sku,
                warehouse_location_id=item_in.warehouse_location_id,
                warehouse_location_name=loc_name,
                quantity_received=item_in.quantity_received,
                quantity_accepted=item_in.quantity_accepted,
                quantity_damaged=item_in.quantity_damaged,
                batch_number=item_in.batch_number,
                expiry_date=item_in.expiry_date,
                unit_cost=item_in.unit_cost,
                notes=item_in.notes,
            )
        )

    # Update PO status if linked
    if payload.purchase_order_id:
        po = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == payload.purchase_order_id))).scalar_one_or_none()
        if po:
            po.status = "Completed" if all_po_items_completed else "Partial"

    # Compute Three-Way Match Status
    match_result = await InventoryService.compute_three_way_match(db, grn)
    grn.match_status = match_result.overall_match_status

    await db.commit()
    await db.refresh(grn)

    po_num = None
    if grn.purchase_order_id:
        po_obj = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == grn.purchase_order_id))).scalar_one_or_none()
        po_num = po_obj.po_number if po_obj else None

    return GoodsReceivedNoteResponse(
        id=grn.id,
        branch_id=grn.branch_id,
        purchase_order_id=grn.purchase_order_id,
        po_number=po_num,
        supplier_id=grn.supplier_id,
        supplier_name=supplier.name,
        grn_number=grn.grn_number,
        status=grn.status,
        received_date=grn.received_date,
        vendor_invoice_no=grn.vendor_invoice_no,
        vendor_invoice_date=grn.vendor_invoice_date,
        vendor_invoice_amount=grn.vendor_invoice_amount,
        match_status=grn.match_status,
        match_notes=grn.match_notes,
        notes=grn.notes,
        received_by_id=grn.received_by_id,
        items=line_resps,
        created_at=grn.created_at,
        updated_at=grn.updated_at,
    )


@router.get("/grns/{id}/three-way-match", response_model=ThreeWayMatchResponse)
async def get_grn_three_way_match(
    id: str,
    db: AsyncSession = Depends(get_db),
):
    grn = (await db.execute(select(GoodsReceivedNote).where(GoodsReceivedNote.id == id))).scalar_one_or_none()
    if not grn:
        raise HTTPException(status_code=404, detail="Goods received note not found")

    return await InventoryService.compute_three_way_match(db, grn)


# 3. Inter-Branch Stock Transfers
@router.get("/transfers", response_model=List[BranchStockTransferResponse])
async def list_transfers(
    branch_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
):
    from app.models.branch import Branch
    query = select(BranchStockTransfer)
    if status_filter:
        query = query.where(BranchStockTransfer.status == status_filter)
    if branch_id:
        query = query.where(
            or_(
                BranchStockTransfer.source_branch_id == branch_id,
                BranchStockTransfer.destination_branch_id == branch_id,
            )
        )

    transfers = (await db.execute(query.order_by(BranchStockTransfer.created_at.desc()))).scalars().all()

    resp_list = []
    for tr in transfers:
        src = (await db.execute(select(Branch).where(Branch.id == tr.source_branch_id))).scalar_one_or_none()
        dst = (await db.execute(select(Branch).where(Branch.id == tr.destination_branch_id))).scalar_one_or_none()

        lines = (await db.execute(select(BranchStockTransferItem).where(BranchStockTransferItem.transfer_id == tr.id))).scalars().all()
        line_resps = []
        for line in lines:
            inv = (await db.execute(select(InventoryItem).where(InventoryItem.id == line.inventory_item_id))).scalar_one_or_none()
            line_resps.append(
                BranchStockTransferItemResponse(
                    id=line.id,
                    transfer_id=tr.id,
                    inventory_item_id=line.inventory_item_id,
                    item_name=inv.name if inv else None,
                    item_sku=inv.sku if inv else None,
                    quantity_requested=line.quantity_requested,
                    quantity_sent=line.quantity_sent,
                    quantity_received=line.quantity_received,
                )
            )

        resp_list.append(
            BranchStockTransferResponse(
                id=tr.id,
                transfer_number=tr.transfer_number,
                source_branch_id=tr.source_branch_id,
                source_branch_name=src.name if src else None,
                destination_branch_id=tr.destination_branch_id,
                destination_branch_name=dst.name if dst else None,
                status=tr.status,
                carrier_name=tr.carrier_name,
                tracking_reference=tr.tracking_reference,
                notes=tr.notes,
                shipped_at=tr.shipped_at,
                received_at=tr.received_at,
                items=line_resps,
                created_at=tr.created_at,
                updated_at=tr.updated_at,
            )
        )
    return resp_list


@router.post("/transfers", response_model=BranchStockTransferResponse, status_code=status.HTTP_201_CREATED)
async def create_transfer(
    payload: BranchStockTransferCreate,
    db: AsyncSession = Depends(get_db),
):
    from app.models.branch import Branch
    src = (await db.execute(select(Branch).where(Branch.id == payload.source_branch_id))).scalar_one_or_none()
    dst = (await db.execute(select(Branch).where(Branch.id == payload.destination_branch_id))).scalar_one_or_none()
    if not src or not dst:
        raise HTTPException(status_code=400, detail="Invalid source or destination branch")

    tr_count = (await db.execute(select(func.count(BranchStockTransfer.id)))).scalar() or 0
    tr_number = f"TR-{datetime.now().strftime('%Y%m')}-{(tr_count + 1):04d}"

    tr = BranchStockTransfer(
        transfer_number=tr_number,
        source_branch_id=payload.source_branch_id,
        destination_branch_id=payload.destination_branch_id,
        status="requested",
        carrier_name=payload.carrier_name,
        tracking_reference=payload.tracking_reference,
        notes=payload.notes,
    )
    db.add(tr)
    await db.flush()

    line_resps = []
    for item_in in payload.items:
        inv = (await db.execute(select(InventoryItem).where(InventoryItem.id == item_in.inventory_item_id))).scalar_one_or_none()
        if not inv:
            continue

        tr_item = BranchStockTransferItem(
            transfer_id=tr.id,
            inventory_item_id=inv.id,
            quantity_requested=item_in.quantity_requested,
            quantity_sent=0.0,
            quantity_received=0.0,
        )
        db.add(tr_item)
        await db.flush()

        line_resps.append(
            BranchStockTransferItemResponse(
                id=tr_item.id,
                transfer_id=tr.id,
                inventory_item_id=inv.id,
                item_name=inv.name,
                item_sku=inv.sku,
                quantity_requested=tr_item.quantity_requested,
                quantity_sent=0.0,
                quantity_received=0.0,
            )
        )

    await db.commit()
    await db.refresh(tr)

    return BranchStockTransferResponse(
        id=tr.id,
        transfer_number=tr.transfer_number,
        source_branch_id=tr.source_branch_id,
        source_branch_name=src.name,
        destination_branch_id=tr.destination_branch_id,
        destination_branch_name=dst.name,
        status=tr.status,
        carrier_name=tr.carrier_name,
        tracking_reference=tr.tracking_reference,
        notes=tr.notes,
        shipped_at=tr.shipped_at,
        received_at=tr.received_at,
        items=line_resps,
        created_at=tr.created_at,
        updated_at=tr.updated_at,
    )


@router.put("/transfers/{id}/dispatch", response_model=BranchStockTransferResponse)
async def dispatch_transfer(
    id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Mark transfer as in-transit and deduct stock from source branch via TRANSFER_OUT.
    """
    tr = (await db.execute(select(BranchStockTransfer).where(BranchStockTransfer.id == id))).scalar_one_or_none()
    if not tr:
        raise HTTPException(status_code=404, detail="Transfer not found")

    tr.status = "in-transit"
    tr.shipped_at = datetime.now(timezone.utc)

    lines = (await db.execute(select(BranchStockTransferItem).where(BranchStockTransferItem.transfer_id == tr.id))).scalars().all()
    for line in lines:
        line.quantity_sent = line.quantity_requested
        # Deduct from source branch
        await InventoryService.record_stock_movement(
            session=db,
            branch_id=tr.source_branch_id,
            inventory_item_id=line.inventory_item_id,
            movement_type="TRANSFER_OUT",
            quantity_change=-line.quantity_sent,
            reference_type="TRANSFER",
            reference_id=tr.transfer_number,
            notes=f"Dispatched in transfer {tr.transfer_number}",
        )

    await db.commit()
    await db.refresh(tr)
    return await list_transfers(db=db, status_filter=None, branch_id=tr.source_branch_id)


@router.put("/transfers/{id}/receive", response_model=BranchStockTransferResponse)
async def receive_transfer(
    id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Mark transfer as received and add stock to destination branch via TRANSFER_IN.
    """
    tr = (await db.execute(select(BranchStockTransfer).where(BranchStockTransfer.id == id))).scalar_one_or_none()
    if not tr:
        raise HTTPException(status_code=404, detail="Transfer not found")

    tr.status = "received"
    tr.received_at = datetime.now(timezone.utc)

    lines = (await db.execute(select(BranchStockTransferItem).where(BranchStockTransferItem.transfer_id == tr.id))).scalars().all()
    for line in lines:
        line.quantity_received = line.quantity_sent or line.quantity_requested
        # Add to destination branch
        await InventoryService.record_stock_movement(
            session=db,
            branch_id=tr.destination_branch_id,
            inventory_item_id=line.inventory_item_id,
            movement_type="TRANSFER_IN",
            quantity_change=line.quantity_received,
            reference_type="TRANSFER",
            reference_id=tr.transfer_number,
            notes=f"Received via transfer {tr.transfer_number}",
        )

    await db.commit()
    await db.refresh(tr)
    return await list_transfers(db=db, status_filter=None, branch_id=tr.destination_branch_id)


# 4. Scrap / Damage Write-Off
@router.post("/scrap", response_model=ScrapWriteOffResponse, status_code=status.HTTP_201_CREATED)
async def create_scrap_write_off(
    payload: ScrapWriteOffCreate,
    db: AsyncSession = Depends(get_db),
):
    inv = (await db.execute(select(InventoryItem).where(InventoryItem.id == payload.inventory_item_id))).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    branch_id = payload.branch_id or inv.branch_id
    if not branch_id:
        from app.models.branch import Branch
        first_b = (await db.execute(select(Branch).limit(1))).scalar_one_or_none()
        branch_id = first_b.id if first_b else "DEFAULT"

    sc_count = (await db.execute(select(func.count(ScrapWriteOff.id)))).scalar() or 0
    voucher_number = f"SCRAP-{datetime.now().strftime('%Y%m')}-{(sc_count + 1):04d}"

    unit_cost = inv.cost_price or 0.0
    total_cost = round(payload.quantity * unit_cost, 2)

    scrap = ScrapWriteOff(
        branch_id=branch_id,
        inventory_item_id=payload.inventory_item_id,
        warehouse_location_id=payload.warehouse_location_id,
        voucher_number=voucher_number,
        quantity=payload.quantity,
        unit_cost=unit_cost,
        total_cost=total_cost,
        reason_code=payload.reason_code,
        notes=payload.notes,
    )
    db.add(scrap)

    # Deduct stock via WRITE_OFF
    await InventoryService.record_stock_movement(
        session=db,
        branch_id=branch_id,
        inventory_item_id=payload.inventory_item_id,
        movement_type="WRITE_OFF",
        quantity_change=-payload.quantity,
        unit_cost=unit_cost,
        warehouse_location_id=payload.warehouse_location_id,
        reference_type="SCRAP",
        reference_id=voucher_number,
        notes=f"Write-off {voucher_number}: {payload.reason_code}. {payload.notes or ''}".strip(),
    )

    await db.commit()
    await db.refresh(scrap)

    loc_name = None
    if payload.warehouse_location_id:
        loc = (await db.execute(select(WarehouseLocation).where(WarehouseLocation.id == payload.warehouse_location_id))).scalar_one_or_none()
        loc_name = loc.name if loc else None

    return ScrapWriteOffResponse(
        id=scrap.id,
        branch_id=scrap.branch_id,
        voucher_number=scrap.voucher_number,
        inventory_item_id=inv.id,
        item_name=inv.name,
        item_sku=inv.sku,
        warehouse_location_id=scrap.warehouse_location_id,
        warehouse_location_name=loc_name,
        quantity=scrap.quantity,
        unit_cost=scrap.unit_cost,
        total_cost=scrap.total_cost,
        reason_code=scrap.reason_code,
        notes=scrap.notes,
        created_by_id=scrap.created_by_id,
        approved_by_id=scrap.approved_by_id,
        created_at=scrap.created_at,
    )


@router.get("/scrap", response_model=List[ScrapWriteOffResponse])
async def list_scrap_write_offs(
    branch_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(ScrapWriteOff)
    if branch_id:
        query = query.where(ScrapWriteOff.branch_id == branch_id)

    scraps = (await db.execute(query.order_by(ScrapWriteOff.created_at.desc()).limit(limit))).scalars().all()
    resp_list = []
    for sc in scraps:
        inv = (await db.execute(select(InventoryItem).where(InventoryItem.id == sc.inventory_item_id))).scalar_one_or_none()
        loc = (await db.execute(select(WarehouseLocation).where(WarehouseLocation.id == sc.warehouse_location_id))).scalar_one_or_none() if sc.warehouse_location_id else None
        resp_list.append(
            ScrapWriteOffResponse(
                id=sc.id,
                branch_id=sc.branch_id,
                voucher_number=sc.voucher_number,
                inventory_item_id=sc.inventory_item_id,
                item_name=inv.name if inv else None,
                item_sku=inv.sku if inv else None,
                warehouse_location_id=sc.warehouse_location_id,
                warehouse_location_name=loc.name if loc else None,
                quantity=sc.quantity,
                unit_cost=sc.unit_cost,
                total_cost=sc.total_cost,
                reason_code=sc.reason_code,
                notes=sc.notes,
                created_by_id=sc.created_by_id,
                approved_by_id=sc.approved_by_id,
                created_at=sc.created_at,
            )
        )
    return resp_list


# 5. Stocktaking Audits
@router.get("/stocktaking", response_model=List[StocktakingAuditResponse])
async def list_stocktaking_audits(
    branch_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
):
    query = select(StocktakingAudit)
    if branch_id:
        query = query.where(StocktakingAudit.branch_id == branch_id)
    if status_filter:
        query = query.where(StocktakingAudit.status == status_filter)

    audits = (await db.execute(query.order_by(StocktakingAudit.created_at.desc()))).scalars().all()
    resp_list = []
    for audit in audits:
        items = (await db.execute(select(StocktakingItem).where(StocktakingItem.stocktaking_audit_id == audit.id))).scalars().all()
        line_resps = []
        tot_exp = 0.0
        tot_cnt = 0.0
        tot_var = 0.0
        tot_val = 0.0

        for line in items:
            inv = (await db.execute(select(InventoryItem).where(InventoryItem.id == line.inventory_item_id))).scalar_one_or_none()
            loc = (await db.execute(select(WarehouseLocation).where(WarehouseLocation.id == line.warehouse_location_id))).scalar_one_or_none() if line.warehouse_location_id else None
            tot_exp += line.expected_quantity
            tot_cnt += line.counted_quantity
            tot_var += line.variance
            tot_val += line.variance_cost

            line_resps.append(
                StocktakingItemResponse(
                    id=line.id,
                    stocktaking_audit_id=audit.id,
                    inventory_item_id=line.inventory_item_id,
                    item_name=inv.name if inv else None,
                    item_sku=inv.sku if inv else None,
                    item_barcode=inv.barcode if inv else None,
                    warehouse_location_id=line.warehouse_location_id,
                    warehouse_location_name=loc.name if loc else None,
                    expected_quantity=line.expected_quantity,
                    counted_quantity=line.counted_quantity,
                    variance=line.variance,
                    unit_cost=line.unit_cost,
                    variance_cost=line.variance_cost,
                    manager_notes=line.manager_notes,
                    adjustment_status=line.adjustment_status,
                )
            )

        resp_list.append(
            StocktakingAuditResponse(
                id=audit.id,
                branch_id=audit.branch_id,
                audit_number=audit.audit_number,
                audit_type=audit.audit_type,
                status=audit.status,
                notes=audit.notes,
                conducted_by_id=audit.conducted_by_id,
                reviewed_by_id=audit.reviewed_by_id,
                completed_at=audit.completed_at,
                items=line_resps,
                total_expected_qty=tot_exp,
                total_counted_qty=tot_cnt,
                total_variance_qty=tot_var,
                total_variance_value=round(tot_val, 2),
                created_at=audit.created_at,
                updated_at=audit.updated_at,
            )
        )
    return resp_list


@router.post("/stocktaking", response_model=StocktakingAuditResponse, status_code=status.HTTP_201_CREATED)
async def create_stocktaking_audit(
    payload: StocktakingAuditCreate,
    db: AsyncSession = Depends(get_db),
):
    branch_id = payload.branch_id
    if not branch_id:
        from app.models.branch import Branch
        first_b = (await db.execute(select(Branch).limit(1))).scalar_one_or_none()
        branch_id = first_b.id if first_b else "DEFAULT"

    stk_count = (await db.execute(select(func.count(StocktakingAudit.id)))).scalar() or 0
    audit_number = f"STK-{datetime.now().strftime('%Y%m')}-{(stk_count + 1):04d}"

    audit = StocktakingAudit(
        branch_id=branch_id,
        audit_number=audit_number,
        audit_type=payload.audit_type,
        status="in_progress",
        notes=payload.notes,
    )
    db.add(audit)
    await db.flush()

    # Pre-populate items snapshot with expected current stock
    items_res = await db.execute(
        select(InventoryItem).where(
            and_(
                InventoryItem.is_active == True,
                InventoryItem.track_inventory == True,
            )
        )
    )
    items = items_res.scalars().all()
    line_resps = []

    for inv in items:
        expected_qty = await InventoryService.get_current_stock(db, inv.id, branch_id)
        stk_item = StocktakingItem(
            stocktaking_audit_id=audit.id,
            inventory_item_id=inv.id,
            expected_quantity=expected_qty,
            counted_quantity=0.0,
            variance=-expected_qty,  # until counted
            unit_cost=inv.cost_price or 0.0,
            variance_cost=round(-expected_qty * (inv.cost_price or 0.0), 2),
            adjustment_status="pending",
        )
        db.add(stk_item)
        await db.flush()

        line_resps.append(
            StocktakingItemResponse(
                id=stk_item.id,
                stocktaking_audit_id=audit.id,
                inventory_item_id=inv.id,
                item_name=inv.name,
                item_sku=inv.sku,
                item_barcode=inv.barcode,
                warehouse_location_id=None,
                warehouse_location_name=None,
                expected_quantity=expected_qty,
                counted_quantity=0.0,
                variance=-expected_qty,
                unit_cost=inv.cost_price or 0.0,
                variance_cost=round(-expected_qty * (inv.cost_price or 0.0), 2),
                manager_notes=None,
                adjustment_status="pending",
            )
        )

    await db.commit()
    await db.refresh(audit)

    return StocktakingAuditResponse(
        id=audit.id,
        branch_id=audit.branch_id,
        audit_number=audit.audit_number,
        audit_type=audit.audit_type,
        status=audit.status,
        notes=audit.notes,
        conducted_by_id=audit.conducted_by_id,
        reviewed_by_id=audit.reviewed_by_id,
        completed_at=audit.completed_at,
        items=line_resps,
        total_expected_qty=sum(i.expected_quantity for i in line_resps),
        total_counted_qty=0.0,
        total_variance_qty=sum(i.variance for i in line_resps),
        total_variance_value=sum(i.variance_cost for i in line_resps),
        created_at=audit.created_at,
        updated_at=audit.updated_at,
    )


@router.post("/stocktaking/{id}/scan", response_model=StocktakingItemResponse)
async def log_stocktake_scan(
    id: str,
    payload: StocktakingCountScan,
    db: AsyncSession = Depends(get_db),
):
    audit = (await db.execute(select(StocktakingAudit).where(StocktakingAudit.id == id))).scalar_one_or_none()
    if not audit:
        raise HTTPException(status_code=404, detail="Stocktake audit not found")
    if audit.status == "completed":
        raise HTTPException(status_code=400, detail="Cannot edit a completed stocktake audit")

    stk_item = (await db.execute(
        select(StocktakingItem).where(
            and_(
                StocktakingItem.stocktaking_audit_id == audit.id,
                StocktakingItem.inventory_item_id == payload.inventory_item_id,
            )
        )
    )).scalar_one_or_none()

    if not stk_item:
        inv = (await db.execute(select(InventoryItem).where(InventoryItem.id == payload.inventory_item_id))).scalar_one_or_none()
        if not inv:
            raise HTTPException(status_code=404, detail="Inventory item not found")
        expected_qty = await InventoryService.get_current_stock(db, inv.id, audit.branch_id)
        stk_item = StocktakingItem(
            stocktaking_audit_id=audit.id,
            inventory_item_id=inv.id,
            warehouse_location_id=payload.warehouse_location_id,
            expected_quantity=expected_qty,
            counted_quantity=payload.counted_quantity,
            variance=payload.counted_quantity - expected_qty,
            unit_cost=inv.cost_price or 0.0,
            variance_cost=round((payload.counted_quantity - expected_qty) * (inv.cost_price or 0.0), 2),
            manager_notes=payload.manager_notes,
            adjustment_status="pending",
        )
        db.add(stk_item)
    else:
        stk_item.counted_quantity = payload.counted_quantity
        stk_item.variance = payload.counted_quantity - stk_item.expected_quantity
        stk_item.variance_cost = round(stk_item.variance * stk_item.unit_cost, 2)
        if payload.warehouse_location_id:
            stk_item.warehouse_location_id = payload.warehouse_location_id
        if payload.manager_notes:
            stk_item.manager_notes = payload.manager_notes

    await db.commit()
    await db.refresh(stk_item)

    inv = (await db.execute(select(InventoryItem).where(InventoryItem.id == stk_item.inventory_item_id))).scalar_one_or_none()
    loc = (await db.execute(select(WarehouseLocation).where(WarehouseLocation.id == stk_item.warehouse_location_id))).scalar_one_or_none() if stk_item.warehouse_location_id else None

    return StocktakingItemResponse(
        id=stk_item.id,
        stocktaking_audit_id=audit.id,
        inventory_item_id=stk_item.inventory_item_id,
        item_name=inv.name if inv else None,
        item_sku=inv.sku if inv else None,
        item_barcode=inv.barcode if inv else None,
        warehouse_location_id=stk_item.warehouse_location_id,
        warehouse_location_name=loc.name if loc else None,
        expected_quantity=stk_item.expected_quantity,
        counted_quantity=stk_item.counted_quantity,
        variance=stk_item.variance,
        unit_cost=stk_item.unit_cost,
        variance_cost=stk_item.variance_cost,
        manager_notes=stk_item.manager_notes,
        adjustment_status=stk_item.adjustment_status,
    )


@router.post("/stocktaking/{id}/adjust")
async def apply_stocktaking_adjustments(
    id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate stock adjustment voucher and reconcile all physical count variances into StockLedger.
    """
    audit = (await db.execute(select(StocktakingAudit).where(StocktakingAudit.id == id))).scalar_one_or_none()
    if not audit:
        raise HTTPException(status_code=404, detail="Stocktake audit not found")
    if audit.status == "completed":
        raise HTTPException(status_code=400, detail="Stocktake audit is already completed and adjusted")

    count = await InventoryService.execute_stocktake_adjustment(db, audit)
    await db.commit()

    return {
        "status": "success",
        "audit_number": audit.audit_number,
        "adjustments_applied": count,
        "message": f"Successfully posted {count} stock adjustment voucher entries to the stock ledger.",
    }
