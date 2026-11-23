from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.inventory import InventoryItem, WarehouseLocation, StockLedger, StockReservation
from app.models.procurement import PurchaseOrder, PurchaseOrderItem, GoodsReceivedNote, GRNItem
from app.models.transfer import BranchStockTransfer, BranchStockTransferItem
from app.models.scrap import ScrapWriteOff
from app.models.stocktaking import StocktakingAudit, StocktakingItem
from app.schemas.procurement import ThreeWayMatchResponse, ThreeWayMatchLine


class InventoryService:
    @staticmethod
    async def get_current_stock(session: AsyncSession, item_id: str, branch_id: Optional[str] = None) -> float:
        """
        Calculate current stock on hand from the stock ledger.
        """
        query = select(func.coalesce(func.sum(StockLedger.quantity_change), 0.0)).where(
            StockLedger.inventory_item_id == item_id
        )
        if branch_id:
            query = query.where(StockLedger.branch_id == branch_id)
        result = await session.execute(query)
        return float(result.scalar() or 0.0)

    @staticmethod
    async def get_allocated_stock(session: AsyncSession, item_id: str, branch_id: Optional[str] = None) -> float:
        """
        Calculate active reservations for repair tickets or checkout carts.
        """
        query = select(func.coalesce(func.sum(StockReservation.quantity), 0.0)).where(
            and_(
                StockReservation.inventory_item_id == item_id,
                StockReservation.status == "active"
            )
        )
        if branch_id:
            query = query.where(StockReservation.branch_id == branch_id)
        result = await session.execute(query)
        return float(result.scalar() or 0.0)

    @staticmethod
    async def record_stock_movement(
        session: AsyncSession,
        branch_id: str,
        inventory_item_id: str,
        movement_type: str,
        quantity_change: float,
        unit_cost: float = 0.0,
        warehouse_location_id: Optional[str] = None,
        reference_type: Optional[str] = None,
        reference_id: Optional[str] = None,
        notes: Optional[str] = None,
        created_by_id: Optional[str] = None,
    ) -> StockLedger:
        """
        Record an immutable double-entry movement in the stock ledger and update running balance.
        Also updates WAC (Weighted Average Cost) on InventoryItem if inbound purchase.
        """
        current_stock = await InventoryService.get_current_stock(session, inventory_item_id, branch_id)
        new_balance = current_stock + quantity_change

        # WAC Costing Calculation on Inbound Purchases
        if movement_type == "PURCHASE_GRN" and quantity_change > 0:
            item_res = await session.execute(
                select(InventoryItem).where(InventoryItem.id == inventory_item_id)
            )
            item = item_res.scalar_one_or_none()
            if item and item.costing_method == "WAC":
                current_total_val = max(0.0, current_stock) * (item.cost_price or 0.0)
                inbound_val = quantity_change * unit_cost
                combined_qty = max(0.0, current_stock) + quantity_change
                if combined_qty > 0:
                    item.cost_price = round((current_total_val + inbound_val) / combined_qty, 2)
            elif item and item.costing_method == "FIFO":
                # For FIFO, update the latest acquisition benchmark cost
                item.cost_price = unit_cost

        ledger_entry = StockLedger(
            branch_id=branch_id,
            inventory_item_id=inventory_item_id,
            warehouse_location_id=warehouse_location_id,
            movement_type=movement_type,
            quantity_change=quantity_change,
            running_balance=new_balance,
            unit_cost=unit_cost,
            total_cost=round(abs(quantity_change) * unit_cost, 2),
            reference_type=reference_type,
            reference_id=reference_id,
            notes=notes,
            created_by_id=created_by_id,
        )
        session.add(ledger_entry)
        await session.flush()
        return ledger_entry

    @staticmethod
    async def compute_three_way_match(
        session: AsyncSession,
        grn: GoodsReceivedNote,
    ) -> ThreeWayMatchResponse:
        """
        Compare Purchase Order vs GRN accepted/damaged vs Vendor Invoice billed.
        Detects price variance and quantity variance.
        """
        po: Optional[PurchaseOrder] = None
        po_items_map: Dict[str, PurchaseOrderItem] = {}

        if grn.purchase_order_id:
            po_res = await session.execute(
                select(PurchaseOrder).where(PurchaseOrder.id == grn.purchase_order_id)
            )
            po = po_res.scalar_one_or_none()
            if po:
                po_lines_res = await session.execute(
                    select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == po.id)
                )
                for line in po_lines_res.scalars().all():
                    po_items_map[line.inventory_item_id] = line

        # Fetch supplier info
        from app.models.supplier import Supplier
        supplier_res = await session.execute(
            select(Supplier).where(Supplier.id == grn.supplier_id)
        )
        supplier = supplier_res.scalar_one_or_none()
        supplier_name = supplier.name if supplier else "Unknown Supplier"

        # Fetch GRN lines with items
        grn_lines_res = await session.execute(
            select(GRNItem, InventoryItem)
            .join(InventoryItem, GRNItem.inventory_item_id == InventoryItem.id)
            .where(GRNItem.grn_id == grn.id)
        )
        grn_lines = grn_lines_res.all()

        match_lines: List[ThreeWayMatchLine] = []
        overall_match = "MATCHED"
        grn_received_value = 0.0

        for grn_item, inv_item in grn_lines:
            po_item = po_items_map.get(grn_item.inventory_item_id)
            po_qty = po_item.quantity_ordered if po_item else grn_item.quantity_received
            po_cost = po_item.unit_cost if po_item else grn_item.unit_cost
            po_line_total = po_qty * po_cost

            inv_cost = grn_item.unit_cost
            inv_total = grn_item.quantity_accepted * inv_cost
            grn_received_value += inv_total

            qty_variance = grn_item.quantity_accepted - po_qty
            price_variance = inv_cost - po_cost

            line_status = "MATCHED"
            if abs(qty_variance) > 0.001:
                line_status = "QUANTITY_MISMATCH"
                if overall_match == "MATCHED":
                    overall_match = "QUANTITY_MISMATCH"
            if abs(price_variance) > 0.01:
                line_status = "PRICE_MISMATCH"
                overall_match = "PRICE_MISMATCH"

            match_lines.append(
                ThreeWayMatchLine(
                    item_id=inv_item.id,
                    item_name=inv_item.name,
                    sku=inv_item.sku,
                    po_quantity=po_qty,
                    po_unit_cost=po_cost,
                    po_total=round(po_line_total, 2),
                    grn_accepted_quantity=grn_item.quantity_accepted,
                    grn_damaged_quantity=grn_item.quantity_damaged,
                    invoice_unit_cost=inv_cost,
                    invoice_total=round(inv_total, 2),
                    quantity_variance=round(qty_variance, 2),
                    price_variance=round(price_variance, 2),
                    match_status=line_status,
                )
            )

        po_grand_total = po.grand_total if po else grn_received_value
        total_variance_amount = round(grn.vendor_invoice_amount - grn_received_value, 2)

        return ThreeWayMatchResponse(
            po_id=po.id if po else None,
            po_number=po.po_number if po else None,
            grn_id=grn.id,
            grn_number=grn.grn_number,
            supplier_id=grn.supplier_id,
            supplier_name=supplier_name,
            vendor_invoice_no=grn.vendor_invoice_no,
            vendor_invoice_amount=grn.vendor_invoice_amount,
            po_grand_total=po_grand_total,
            grn_received_value=round(grn_received_value, 2),
            total_variance_amount=total_variance_amount,
            overall_match_status=overall_match,
            match_lines=match_lines,
        )

    @staticmethod
    async def execute_stocktake_adjustment(
        session: AsyncSession,
        audit: StocktakingAudit,
        actor_id: Optional[str] = None,
    ) -> int:
        """
        Creates adjustment entries in StockLedger for all lines in the audit where variance != 0.
        """
        items_res = await session.execute(
            select(StocktakingItem).where(StocktakingItem.stocktaking_audit_id == audit.id)
        )
        items = items_res.scalars().all()
        adjustment_count = 0

        for stk_item in items:
            if abs(stk_item.variance) > 0.001 and stk_item.adjustment_status == "pending":
                await InventoryService.record_stock_movement(
                    session=session,
                    branch_id=audit.branch_id,
                    inventory_item_id=stk_item.inventory_item_id,
                    movement_type="STOCKTAKE_ADJUSTMENT",
                    quantity_change=stk_item.variance,
                    unit_cost=stk_item.unit_cost,
                    warehouse_location_id=stk_item.warehouse_location_id,
                    reference_type="STOCKTAKE",
                    reference_id=audit.audit_number,
                    notes=f"Stocktake {audit.audit_number} variance: {stk_item.variance}. {stk_item.manager_notes or ''}".strip(),
                    created_by_id=actor_id,
                )
                stk_item.adjustment_status = "adjusted"
                adjustment_count += 1

        audit.status = "completed"
        audit.completed_at = datetime.now(timezone.utc)
        await session.flush()
        return adjustment_count
