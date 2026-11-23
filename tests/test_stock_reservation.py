import pytest
import secrets
from sqlalchemy import select
from app.models.branch import Branch
from app.models.inventory import InventoryItem, StockReservation
from app.services.inventory_service import InventoryService


@pytest.mark.asyncio
class TestStockReservation:
    async def test_stock_reservation_lifecycle(self, db_session):
        """
        Verify that allocated stock reservations correctly offset available stock
        and transition from active to consumed or cancelled.
        """
        # 1. Fetch branch
        b_res = await db_session.execute(select(Branch).limit(1))
        branch = b_res.scalar_one()

        # 2. Create item
        unique_sku = f"TEST-RES-{secrets.token_hex(3).upper()}"
        item = InventoryItem(
            branch_id=branch.id,
            name="Inverter PCB Controller",
            sku=unique_sku,
            barcode=f"BAR-{unique_sku}",
            category="PCBs",
            unit="PCS",
            cost_price=2000.0,
            retail_price=4500.0,
        )
        db_session.add(item)
        await db_session.flush()

        # 3. Add 10 units to stock ledger
        await InventoryService.record_stock_movement(
            session=db_session,
            branch_id=branch.id,
            inventory_item_id=item.id,
            movement_type="PURCHASE_GRN",
            quantity_change=10.0,
            unit_cost=2000.0,
        )

        on_hand = await InventoryService.get_current_stock(db_session, item.id, branch.id)
        assert on_hand == 10.0

        # No initial reservations
        allocated_before = await InventoryService.get_allocated_stock(db_session, item.id, branch.id)
        assert allocated_before == 0.0

        # 4. Create active reservation of 3 units for a work order
        reservation = StockReservation(
            branch_id=branch.id,
            inventory_item_id=item.id,
            quantity=3.0,
            reserved_for_type="ticket",
            reserved_for_id="TK-TEST-001",
            status="active",
        )
        db_session.add(reservation)
        await db_session.flush()

        # 5. Check allocated stock & available stock
        allocated_after = await InventoryService.get_allocated_stock(db_session, item.id, branch.id)
        assert allocated_after == 3.0

        available_stock = on_hand - allocated_after
        assert available_stock == 7.0

        # 6. Consume reservation on repair completion
        reservation.status = "consumed"
        await db_session.flush()

        # Allocated stock drops back to 0 because status is no longer "active"
        allocated_consumed = await InventoryService.get_allocated_stock(db_session, item.id, branch.id)
        assert allocated_consumed == 0.0
