import pytest
import secrets
from sqlalchemy import select
from app.models.branch import Branch
from app.models.inventory import InventoryItem, StockLedger
from app.services.inventory_service import InventoryService


@pytest.mark.asyncio
class TestLedgerBalance:
    async def test_stock_movement_and_running_balance(self, db_session):
        """
        Verify immutable double-entry stock ledger movements and running balance updates.
        """
        # 1. Fetch or create branch
        b_res = await db_session.execute(select(Branch).limit(1))
        branch = b_res.scalar_one()

        # 2. Create test item with WAC costing
        unique_sku = f"TEST-SPARE-{secrets.token_hex(3).upper()}"
        item = InventoryItem(
            branch_id=branch.id,
            name="Universal Drain Pump 220V",
            sku=unique_sku,
            barcode=f"BAR-{unique_sku}",
            category="Pumps",
            unit="PCS",
            cost_price=500.0,
            retail_price=1200.0,
            costing_method="WAC",
        )
        db_session.add(item)
        await db_session.flush()

        # 3. Initial Inbound Movement (PURCHASE_GRN: +10 units @ 500)
        e1 = await InventoryService.record_stock_movement(
            session=db_session,
            branch_id=branch.id,
            inventory_item_id=item.id,
            movement_type="PURCHASE_GRN",
            quantity_change=10.0,
            unit_cost=500.0,
            notes="Initial stock purchase",
        )
        assert e1.running_balance == 10.0
        assert e1.quantity_change == 10.0

        current_stock = await InventoryService.get_current_stock(db_session, item.id, branch.id)
        assert current_stock == 10.0

        # 4. Outbound POS Checkout (SALE_POS: -2 units)
        e2 = await InventoryService.record_stock_movement(
            session=db_session,
            branch_id=branch.id,
            inventory_item_id=item.id,
            movement_type="SALE_POS",
            quantity_change=-2.0,
            unit_cost=500.0,
            notes="Counter POS checkout",
        )
        assert e2.running_balance == 8.0

        current_stock = await InventoryService.get_current_stock(db_session, item.id, branch.id)
        assert current_stock == 8.0

        # 5. Work Order Consumption (WORK_ORDER_USED: -3 units)
        e3 = await InventoryService.record_stock_movement(
            session=db_session,
            branch_id=branch.id,
            inventory_item_id=item.id,
            movement_type="WORK_ORDER_USED",
            quantity_change=-3.0,
            unit_cost=500.0,
            notes="Consumed in repair ticket",
        )
        assert e3.running_balance == 5.0

        current_stock = await InventoryService.get_current_stock(db_session, item.id, branch.id)
        assert current_stock == 5.0

        # 6. Second Inbound Batch at higher price (+5 units @ 600) -> WAC test
        # Current: 5 units @ 500 = 2500. Inbound: 5 units @ 600 = 3000. Total: 10 units @ 550.
        e4 = await InventoryService.record_stock_movement(
            session=db_session,
            branch_id=branch.id,
            inventory_item_id=item.id,
            movement_type="PURCHASE_GRN",
            quantity_change=5.0,
            unit_cost=600.0,
            notes="Batch 2 PO delivery",
        )
        assert e4.running_balance == 10.0
        assert item.cost_price == 550.0  # Weighted Average Cost recalculated!
