import secrets
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from fastapi import HTTPException
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.base import utc_now
from app.models.ticket import (
    Ticket,
    TicketPart,
    TicketLabor,
    TicketMedia,
    TicketEstimate,
    TicketSubcontract,
    generate_tracking_token,
)
from app.models.client import Client
from app.models.asset import Asset
from app.models.user import User
from app.models.branch import Branch
from app.models.inventory import InventoryItem, StockReservation, StockLedger
from app.models.service_catalog import ServiceCatalogItem
from app.models.procurement import PurchaseOrder, PurchaseOrderItem
from app.models.supplier import Supplier
from app.models.client_interaction import ClientInteraction
from app.services.inventory_service import InventoryService


class TicketService:
    @staticmethod
    async def generate_ticket_number(session: AsyncSession, branch_id: str) -> str:
        """
        Generate human-friendly sequential ticket code: e.g. TK-202611-0001
        """
        now = datetime.now(timezone.utc)
        prefix = f"TK-{now.strftime('%Y%m')}"
        query = select(func.count(Ticket.id)).where(Ticket.ticket_number.like(f"{prefix}-%"))
        res = await session.execute(query)
        count = (res.scalar() or 0) + 1
        return f"{prefix}-{count:04d}"

    @staticmethod
    async def recompute_ticket_totals(ticket: Ticket) -> None:
        """
        Recompute parts total, labor total, tax total, grand total, and balance due.
        """
        parts_sub = sum(p.total_price for p in ticket.parts) if ticket.parts else 0.0
        labor_sub = sum(l.total_price for l in ticket.labor_items) if ticket.labor_items else 0.0
        
        ticket.total_parts_cost = round(parts_sub, 2)
        ticket.total_labor_cost = round(labor_sub, 2)
        subtotal = ticket.total_parts_cost + ticket.total_labor_cost
        
        # Calculate grand total minus discount plus taxes already bundled in line totals
        ticket.grand_total = round(max(0.0, subtotal - (ticket.discount_amount or 0.0)), 2)
        ticket.balance_due = round(max(0.0, ticket.grand_total - (ticket.paid_amount or 0.0)), 2)

    @staticmethod
    async def check_threshold_pause(ticket: Ticket) -> None:
        """
        Threshold Pause: If grand total or estimated cost exceeds customer_max_repair_budget,
        halt ticket workflow and require explicit customer authorization.
        """
        if ticket.customer_max_repair_budget and ticket.customer_max_repair_budget > 0:
            if ticket.grand_total > ticket.customer_max_repair_budget:
                ticket.is_paused = True
                ticket.pause_reason = (
                    f"Cost ₹{ticket.grand_total:.2f} exceeds customer authorized ceiling of "
                    f"₹{ticket.customer_max_repair_budget:.2f}. Awaiting customer approval."
                )

    @staticmethod
    async def get_ticket_with_relations(session: AsyncSession, ticket_id: str) -> Optional[Ticket]:
        query = (
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(
                selectinload(Ticket.parts).selectinload(TicketPart.item),
                selectinload(Ticket.labor_items).selectinload(TicketLabor.assigned_tech),
                selectinload(Ticket.media),
                selectinload(Ticket.estimates),
                selectinload(Ticket.subcontracts),
                selectinload(Ticket.client),
                selectinload(Ticket.asset),
                selectinload(Ticket.branch),
                selectinload(Ticket.assigned_tech),
            )
        )
        res = await session.execute(query)
        return res.scalar_one_or_none()

    @staticmethod
    async def add_part(
        session: AsyncSession,
        ticket: Ticket,
        inventory_item_id: str,
        quantity: float,
        unit_price: Optional[float] = None,
        tax_rate: Optional[float] = None,
        notes: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> TicketPart:
        """
        Add spare part to ticket.
        - Check available stock on hand.
        - If stock is insufficient, set ticket to "Spare Wait" and auto-create draft PurchaseOrder.
        - If stock is available, create active StockReservation.
        - Recompute totals & check threshold pause.
        """
        item_res = await session.execute(
            select(InventoryItem).where(InventoryItem.id == inventory_item_id)
        )
        item = item_res.scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="Inventory item not found")

        u_price = unit_price if unit_price is not None else item.retail_price
        t_rate = tax_rate if tax_rate is not None else item.tax_rate
        line_total = round(quantity * u_price * (1 + t_rate / 100.0), 2)

        # Check stock availability
        current_stock = await InventoryService.get_current_stock(session, item.id, ticket.branch_id)
        allocated_stock = await InventoryService.get_allocated_stock(session, item.id, ticket.branch_id)
        available_stock = current_stock - allocated_stock

        reservation_id = None
        is_reserved = False

        if available_stock < quantity:
            # Stock shortage gate triggered!
            ticket.status = "spare_wait"
            ticket.is_paused = True
            ticket.pause_reason = f"Stock Shortage: {item.name} (Required: {quantity}, Available: {max(0.0, available_stock)}). Auto-drafted PO."

            # Automatically create draft PurchaseOrder for procurement
            supplier_res = await session.execute(
                select(Supplier).where(Supplier.is_active == True).limit(1)
            )
            default_supplier = supplier_res.scalar_one_or_none()
            if default_supplier:
                po_num = f"PO-AUTO-{secrets.token_hex(3).upper()}"
                shortage_qty = round(quantity - max(0.0, available_stock) + item.min_stock_level, 2)
                draft_po = PurchaseOrder(
                    branch_id=ticket.branch_id,
                    supplier_id=default_supplier.id,
                    po_number=po_num,
                    status="draft",
                    notes=f"Auto-generated draft PO for Ticket {ticket.ticket_number} (Item: {item.sku} - {item.name})",
                    subtotal=round(shortage_qty * item.cost_price, 2),
                    grand_total=round(shortage_qty * item.cost_price * (1 + item.tax_rate / 100.0), 2),
                    created_by_id=user_id,
                )
                session.add(draft_po)
                await session.flush()

                po_item = PurchaseOrderItem(
                    purchase_order_id=draft_po.id,
                    inventory_item_id=item.id,
                    quantity_ordered=shortage_qty,
                    quantity_received=0.0,
                    unit_cost=item.cost_price,
                    tax_rate=item.tax_rate,
                    tax_amount=round(shortage_qty * item.cost_price * (item.tax_rate / 100.0), 2),
                    total_amount=draft_po.grand_total,
                )
                session.add(po_item)
        else:
            # Stock is available: Reserve it
            reservation = StockReservation(
                branch_id=ticket.branch_id,
                inventory_item_id=item.id,
                quantity=quantity,
                reserved_for_type="ticket",
                reserved_for_id=ticket.id,
                status="active",
            )
            session.add(reservation)
            await session.flush()
            reservation_id = reservation.id
            is_reserved = True

        part = TicketPart(
            ticket_id=ticket.id,
            inventory_item_id=item.id,
            quantity=quantity,
            unit_cost=item.cost_price,
            unit_price=u_price,
            tax_rate=t_rate,
            total_price=line_total,
            is_reserved=is_reserved,
            reservation_id=reservation_id,
            notes=notes,
        )
        part.item = item
        session.add(part)
        await session.flush()

        ticket.parts.append(part)
        await TicketService.recompute_ticket_totals(ticket)
        await TicketService.check_threshold_pause(ticket)
        await session.flush()

        return part

    @staticmethod
    async def add_labor(
        session: AsyncSession,
        ticket: Ticket,
        name: str,
        labor_price: float,
        service_catalog_item_id: Optional[str] = None,
        sac_code: str = "9987",
        tax_rate: float = 18.0,
        commission_rate: float = 0.0,
        assigned_tech_id: Optional[str] = None,
        duration_minutes: int = 30,
    ) -> TicketLabor:
        """
        Add labor operation to ticket with technician commission tracking.
        """
        line_total = round(labor_price * (1 + tax_rate / 100.0), 2)
        commission_amt = round(labor_price * (commission_rate / 100.0), 2)

        labor = TicketLabor(
            ticket_id=ticket.id,
            service_catalog_item_id=service_catalog_item_id,
            name=name,
            sac_code=sac_code,
            labor_price=labor_price,
            tax_rate=tax_rate,
            total_price=line_total,
            commission_rate=commission_rate,
            commission_amount=commission_amt,
            assigned_tech_id=assigned_tech_id or ticket.assigned_tech_id,
            duration_minutes=duration_minutes,
            status="pending",
        )
        session.add(labor)
        await session.flush()

        ticket.labor_items.append(labor)
        await TicketService.recompute_ticket_totals(ticket)
        await TicketService.check_threshold_pause(ticket)
        await session.flush()

        return labor

    @staticmethod
    async def create_estimate(
        session: AsyncSession,
        ticket: Ticket,
        customer_notes: Optional[str] = None,
        custom_line_items: Optional[List[Dict[str, Any]]] = None,
    ) -> TicketEstimate:
        """
        Generate a formal estimate with a 128-bit secure 1-click tokenized customer approval link.
        """
        now = datetime.now(timezone.utc)
        est_number = f"EST-{ticket.ticket_number}-{len(ticket.estimates) + 1:02d}"

        # Snapshot line items
        line_items = []
        if custom_line_items:
            line_items = custom_line_items
        else:
            for p in ticket.parts:
                line_items.append({
                    "type": "part",
                    "description": p.item.name if p.item else "Spare Part",
                    "quantity": p.quantity,
                    "unit_price": p.unit_price,
                    "tax_rate": p.tax_rate,
                    "total_price": p.total_price,
                })
            for l in ticket.labor_items:
                line_items.append({
                    "type": "labor",
                    "description": l.name,
                    "quantity": 1,
                    "unit_price": l.labor_price,
                    "tax_rate": l.tax_rate,
                    "total_price": l.total_price,
                })

        parts_sub = sum(item["total_price"] for item in line_items if item.get("type") == "part")
        labor_sub = sum(item["total_price"] for item in line_items if item.get("type") == "labor")
        grand = round(parts_sub + labor_sub, 2)

        estimate = TicketEstimate(
            ticket_id=ticket.id,
            estimate_number=est_number,
            approval_token=generate_tracking_token(),
            approval_status="pending",
            parts_subtotal=parts_sub,
            labor_subtotal=labor_sub,
            tax_total=round(grand * 0.18, 2),
            grand_total=grand,
            line_items=line_items,
            customer_notes=customer_notes,
        )
        session.add(estimate)
        await session.flush()
        return estimate

    @staticmethod
    async def approve_or_reject_estimate(
        session: AsyncSession,
        token: str,
        action: str,
        customer_ip: Optional[str] = None,
        rejection_reason: Optional[str] = None,
    ) -> TicketEstimate:
        """
        Process 1-click customer approval or rejection of estimate from public web token.
        """
        est_res = await session.execute(
            select(TicketEstimate)
            .where(TicketEstimate.approval_token == token)
            .options(selectinload(TicketEstimate.ticket))
        )
        estimate = est_res.scalar_one_or_none()
        if not estimate:
            raise HTTPException(status_code=404, detail="Invalid or expired estimate token")

        if estimate.approval_status != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Estimate has already been {estimate.approval_status}"
            )

        ticket = estimate.ticket

        if action.lower() == "approve":
            estimate.approval_status = "approved"
            estimate.approved_at = utc_now()
            estimate.customer_ip = customer_ip

            # Unpause ticket if it was paused for approval
            if ticket and ticket.is_paused and "Awaiting customer approval" in (ticket.pause_reason or ""):
                ticket.is_paused = False
                ticket.pause_reason = None
                ticket.status = "in_progress"
        elif action.lower() == "reject":
            estimate.approval_status = "rejected"
            estimate.rejection_reason = rejection_reason or "Customer rejected estimate"
            if ticket:
                ticket.is_paused = True
                ticket.pause_reason = f"Estimate {estimate.estimate_number} rejected by customer: {estimate.rejection_reason}"
        else:
            raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")

        await session.flush()
        return estimate

    @staticmethod
    async def execute_stock_consumption_on_completion(session: AsyncSession, ticket: Ticket) -> None:
        """
        When ticket reaches completed/delivered status, record WORK_ORDER_USED in StockLedger
        for all reserved parts and mark reservations as consumed.
        """
        for part in ticket.parts:
            if part.is_reserved and not part.is_consumed:
                # Deduct stock in double-entry ledger
                await InventoryService.record_stock_movement(
                    session=session,
                    branch_id=ticket.branch_id,
                    inventory_item_id=part.inventory_item_id,
                    movement_type="WORK_ORDER_USED",
                    quantity_change=-part.quantity,
                    unit_cost=part.unit_cost,
                    reference_type="TICKET",
                    reference_id=ticket.ticket_number,
                    notes=f"Consumed in repair ticket {ticket.ticket_number}",
                )
                if part.reservation_id:
                    res_obj = await session.get(StockReservation, part.reservation_id)
                    if res_obj:
                        res_obj.status = "consumed"
                part.is_consumed = True
                part.consumed_at = utc_now()

    @staticmethod
    async def process_handover(
        session: AsyncSession,
        ticket: Ticket,
        recipient: str,
        payment_method: str = "cash",
        payment_amount: float = 0.0,
        signature: Optional[str] = None,
        manager_override: bool = False,
        notes: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Ticket:
        """
        Closure Gate Verification & Delivery Handover:
        - Block "Delivered" if balance_due > 0 unless manager_override is provided.
        - Record multi-tender payment settlement into ticket paid_amount.
        - Deduct consumed parts from stock ledger.
        - Stamp delivery timestamp & customer signature.
        """
        total_paying = (ticket.paid_amount or 0.0) + payment_amount
        remaining_balance = round(max(0.0, ticket.grand_total - total_paying), 2)

        if remaining_balance > 0 and not manager_override:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Closure gate blocked: Ticket {ticket.ticket_number} has an outstanding "
                    f"balance of ₹{remaining_balance:.2f}. Settle payment in full or provide "
                    f"manager override to complete delivery."
                )
            )

        ticket.paid_amount = round(total_paying, 2)
        ticket.balance_due = remaining_balance
        ticket.status = "delivered"
        ticket.handover_at = utc_now()
        ticket.handover_recipient = recipient
        ticket.handover_signature = signature
        ticket.handover_notes = notes

        # Deduct parts
        await TicketService.execute_stock_consumption_on_completion(session, ticket)

        # Log interaction on client timeline
        interaction = ClientInteraction(
            client_id=ticket.client_id,
            branch_id=ticket.branch_id,
            actor_id=user_id,
            actor_name="Staff",
            type="payment",
            direction="internal",
            title=f"Ticket {ticket.ticket_number} Delivered to {recipient}",
            details=(
                f"Completed delivery. Settled ₹{payment_amount:.2f} via {payment_method}. "
                f"Remaining balance: ₹{remaining_balance:.2f}."
            ),
            extra_metadata={"ticket_id": ticket.id, "payment_method": payment_method, "payment_amount": payment_amount},
        )
        session.add(interaction)
        await session.flush()

        return ticket
