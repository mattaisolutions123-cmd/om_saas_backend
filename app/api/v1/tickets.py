from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, desc
from sqlalchemy.orm import selectinload

from app.db.session import get_db
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
from app.models.branch import Branch
from app.models.user import User
from app.models.inventory import InventoryItem, StockReservation
from app.models.service_catalog import ServiceCatalogItem
from app.models.client_interaction import ClientInteraction
from app.models.pipeline import StatusPipeline, StatusDefinition, StatusTransition
from app.schemas.ticket import (
    TicketCreate,
    TicketUpdate,
    TicketResponse,
    TicketPartCreate,
    TicketPartResponse,
    TicketLaborCreate,
    TicketLaborResponse,
    TicketMediaCreate,
    TicketMediaResponse,
    TicketEstimateCreate,
    TicketEstimateResponse,
    EstimateApprovalPayload,
    TicketSubcontractCreate,
    TicketSubcontractUpdate,
    TicketSubcontractResponse,
    QAChecklistUpdate,
    TicketHandoverPayload,
    TicketPublicTrackingResponse,
)
from app.services.ticket_service import TicketService
from app.services.inventory_service import InventoryService
from app.services.audit import log_audit_event
from app.models.base import utc_now

router = APIRouter(prefix="/tickets", tags=["Tickets & Work Orders"])


def _serialize_ticket(t: Ticket) -> Dict[str, Any]:
    """Helper to serialize ORM Ticket into schema dict with joined relations."""
    client_name = t.client.name if t.client else None
    client_phone = t.client.phone if t.client else None
    asset_name = t.asset.name if t.asset else None
    asset_identifier = t.asset.identifier if t.asset else None
    assigned_tech_name = t.assigned_tech.full_name if t.assigned_tech else None
    branch_name = t.branch.name if t.branch else None

    parts_data = []
    for p in t.parts:
        parts_data.append({
            "id": p.id,
            "ticket_id": p.ticket_id,
            "inventory_item_id": p.inventory_item_id,
            "item_name": p.item.name if p.item else None,
            "item_sku": p.item.sku if p.item else None,
            "quantity": p.quantity,
            "unit_cost": p.unit_cost,
            "unit_price": p.unit_price,
            "tax_rate": p.tax_rate,
            "total_price": p.total_price,
            "is_reserved": p.is_reserved,
            "reservation_id": p.reservation_id,
            "is_consumed": p.is_consumed,
            "consumed_at": p.consumed_at,
            "notes": p.notes,
            "created_at": p.created_at,
        })

    labor_data = []
    for l in t.labor_items:
        labor_data.append({
            "id": l.id,
            "ticket_id": l.ticket_id,
            "service_catalog_item_id": l.service_catalog_item_id,
            "name": l.name,
            "sac_code": l.sac_code,
            "labor_price": l.labor_price,
            "tax_rate": l.tax_rate,
            "total_price": l.total_price,
            "commission_rate": l.commission_rate,
            "commission_amount": l.commission_amount,
            "assigned_tech_id": l.assigned_tech_id,
            "assigned_tech_name": l.assigned_tech.full_name if l.assigned_tech else None,
            "duration_minutes": l.duration_minutes,
            "status": l.status,
            "completed_at": l.completed_at,
            "created_at": l.created_at,
        })

    media_data = [
        {
            "id": m.id,
            "ticket_id": m.ticket_id,
            "media_type": m.media_type,
            "file_url": m.file_url,
            "file_name": m.file_name,
            "file_size_kb": m.file_size_kb,
            "notes": m.notes,
            "uploaded_by_id": m.uploaded_by_id,
            "created_at": m.created_at,
        }
        for m in t.media
    ]

    estimates_data = [
        {
            "id": e.id,
            "ticket_id": e.ticket_id,
            "estimate_number": e.estimate_number,
            "approval_token": e.approval_token,
            "approval_status": e.approval_status,
            "parts_subtotal": e.parts_subtotal,
            "labor_subtotal": e.labor_subtotal,
            "tax_total": e.tax_total,
            "grand_total": e.grand_total,
            "line_items": e.line_items or [],
            "customer_notes": e.customer_notes,
            "approved_at": e.approved_at,
            "customer_ip": e.customer_ip,
            "rejection_reason": e.rejection_reason,
            "expires_at": e.expires_at,
            "created_at": e.created_at,
        }
        for e in t.estimates
    ]

    subcontracts_data = [
        {
            "id": s.id,
            "ticket_id": s.ticket_id,
            "vendor_name": s.vendor_name,
            "vendor_phone": s.vendor_phone,
            "task_description": s.task_description,
            "cost": s.cost,
            "charged_to_customer": s.charged_to_customer,
            "status": s.status,
            "dispatch_date": s.dispatch_date,
            "expected_return_date": s.expected_return_date,
            "actual_return_date": s.actual_return_date,
            "notes": s.notes,
            "created_at": s.created_at,
        }
        for s in t.subcontracts
    ]

    return {
        "id": t.id,
        "ticket_number": t.ticket_number,
        "branch_id": t.branch_id,
        "client_id": t.client_id,
        "asset_id": t.asset_id,
        "ticket_type": t.ticket_type,
        "pipeline_id": t.pipeline_id,
        "status": t.status,
        "priority": t.priority,
        "assigned_tech_id": t.assigned_tech_id,
        "intake_source": t.intake_source,
        "intake_notes": t.intake_notes,
        "problem_reported": t.problem_reported,
        "diagnosis_notes": t.diagnosis_notes,
        "promised_delivery_date": t.promised_delivery_date,
        "customer_max_repair_budget": t.customer_max_repair_budget,
        "advance_deposit": t.advance_deposit,
        "total_parts_cost": t.total_parts_cost,
        "total_labor_cost": t.total_labor_cost,
        "tax_total": t.tax_total,
        "discount_amount": t.discount_amount,
        "grand_total": t.grand_total,
        "paid_amount": t.paid_amount,
        "balance_due": t.balance_due,
        "is_paused": t.is_paused,
        "pause_reason": t.pause_reason,
        "tracking_token": t.tracking_token,
        "dynamic_fields": t.dynamic_fields or {},
        "qa_status": t.qa_status,
        "qa_checklist": t.qa_checklist or [],
        "rma_details": t.rma_details or {},
        "handover_at": t.handover_at,
        "handover_signature": t.handover_signature,
        "handover_recipient": t.handover_recipient,
        "handover_notes": t.handover_notes,
        "created_by_id": t.created_by_id,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
        "client_name": client_name,
        "client_phone": client_phone,
        "asset_name": asset_name,
        "asset_identifier": asset_identifier,
        "assigned_tech_name": assigned_tech_name,
        "branch_name": branch_name,
        "parts": parts_data,
        "labor_items": labor_data,
        "media": media_data,
        "estimates": estimates_data,
        "subcontracts": subcontracts_data,
    }


# 1. List Tickets
@router.get("", response_model=List[TicketResponse])
async def list_tickets(
    branch_id: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    assigned_tech_id: Optional[str] = Query(None),
    ticket_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Ticket)
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
        .order_by(Ticket.created_at.desc())
    )

    if branch_id:
        query = query.where(Ticket.branch_id == branch_id)
    if client_id:
        query = query.where(Ticket.client_id == client_id)
    if status:
        query = query.where(Ticket.status == status)
    if priority:
        query = query.where(Ticket.priority == priority)
    if assigned_tech_id:
        query = query.where(Ticket.assigned_tech_id == assigned_tech_id)
    if ticket_type:
        query = query.where(Ticket.ticket_type == ticket_type)
    if search:
        search_filter = or_(
            Ticket.ticket_number.ilike(f"%{search}%"),
            Ticket.problem_reported.ilike(f"%{search}%"),
            Ticket.diagnosis_notes.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)

    tickets = (await db.execute(query)).scalars().all()
    return [_serialize_ticket(t) for t in tickets]


# 2. Public Tracking Endpoint (128-bit Token, Non-Authenticated)
@router.get("/track/{token}", response_model=TicketPublicTrackingResponse)
async def public_track_ticket(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Ticket)
        .where(Ticket.tracking_token == token)
        .options(
            selectinload(Ticket.estimates),
            selectinload(Ticket.media),
            selectinload(Ticket.client),
            selectinload(Ticket.asset),
            selectinload(Ticket.branch),
        )
    )
    ticket = (await db.execute(query)).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Work order tracking record not found")

    before_urls = [m.file_url for m in ticket.media if m.media_type == "before"]
    after_urls = [m.file_url for m in ticket.media if m.media_type == "after"]

    estimates_data = [
        TicketEstimateResponse.model_validate(e)
        for e in ticket.estimates
    ]

    return TicketPublicTrackingResponse(
        ticket_number=ticket.ticket_number,
        status=ticket.status,
        priority=ticket.priority,
        ticket_type=ticket.ticket_type,
        problem_reported=ticket.problem_reported,
        diagnosis_notes=ticket.diagnosis_notes,
        promised_delivery_date=ticket.promised_delivery_date,
        grand_total=ticket.grand_total,
        paid_amount=ticket.paid_amount,
        balance_due=ticket.balance_due,
        is_paused=ticket.is_paused,
        pause_reason=ticket.pause_reason,
        qa_status=ticket.qa_status,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        client_name=ticket.client.name if ticket.client else "Customer",
        asset_name=ticket.asset.name if ticket.asset else "Device",
        asset_identifier=ticket.asset.identifier if ticket.asset else None,
        branch_name=ticket.branch.name if ticket.branch else None,
        estimates=estimates_data,
        before_media_urls=before_urls,
        after_media_urls=after_urls,
    )


# 3. Create Ticket (Intake)
@router.post("", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreate,
    db: AsyncSession = Depends(get_db),
):
    # Resolve branch
    branch_id = payload.branch_id
    if not branch_id:
        branch_res = await db.execute(select(Branch).limit(1))
        branch = branch_res.scalar_one_or_none()
        if not branch:
            raise HTTPException(status_code=400, detail="No active branch found. Please provide branch_id.")
        branch_id = branch.id

    # Verify Client
    client = await db.get(Client, payload.client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Verify Asset if provided
    if payload.asset_id:
        asset = await db.get(Asset, payload.asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail="Asset not found")

    # Generate sequential ticket number
    ticket_num = await TicketService.generate_ticket_number(db, branch_id)
    track_token = generate_tracking_token()

    ticket = Ticket(
        ticket_number=ticket_num,
        branch_id=branch_id,
        client_id=payload.client_id,
        asset_id=payload.asset_id,
        ticket_type=payload.ticket_type,
        pipeline_id=payload.pipeline_id,
        status=payload.status or "intake",
        priority=payload.priority,
        assigned_tech_id=payload.assigned_tech_id,
        intake_source=payload.intake_source,
        intake_notes=payload.intake_notes,
        problem_reported=payload.problem_reported,
        diagnosis_notes=payload.diagnosis_notes,
        promised_delivery_date=payload.promised_delivery_date,
        customer_max_repair_budget=payload.customer_max_repair_budget,
        advance_deposit=payload.advance_deposit,
        paid_amount=payload.advance_deposit,
        balance_due=0.0,
        tracking_token=track_token,
        dynamic_fields=payload.dynamic_fields,
        rma_details=payload.rma_details,
    )

    db.add(ticket)
    await db.flush()

    # Log Client Interaction
    interaction = ClientInteraction(
        client_id=client.id,
        branch_id=branch_id,
        type="note",
        direction="inbound",
        title=f"Ticket {ticket_num} Logged ({payload.ticket_type})",
        details=f"Problem: {payload.problem_reported or 'General service'}. Advance Paid: ₹{payload.advance_deposit:.2f}.",
        extra_metadata={"ticket_id": ticket.id, "ticket_number": ticket_num},
    )
    db.add(interaction)

    await log_audit_event(
        db=db,
        action="create_ticket",
        entity="ticket",
        entity_id=ticket.id,
        before_state=None,
        after_state={"ticket_number": ticket_num, "client_id": client.id},
    )

    await db.commit()
    reloaded = await TicketService.get_ticket_with_relations(db, ticket.id)
    return _serialize_ticket(reloaded)


# 4. Get Ticket Detail
@router.get("/{id}", response_model=TicketResponse)
async def get_ticket(
    id: str,
    db: AsyncSession = Depends(get_db),
):
    ticket = await TicketService.get_ticket_with_relations(db, id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return _serialize_ticket(ticket)


# 5. Update Ticket
@router.put("/{id}", response_model=TicketResponse)
async def update_ticket(
    id: str,
    payload: TicketUpdate,
    db: AsyncSession = Depends(get_db),
):
    ticket = await TicketService.get_ticket_with_relations(db, id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Closure Gate Verification: If setting status to 'delivered' or 'closed'
    if payload.status and payload.status.lower() in ["delivered", "closed"]:
        if ticket.balance_due > 0 and not payload.manager_override:
            raise HTTPException(
                status_code=400,
                detail=f"Closure gate blocked: Ticket {ticket.ticket_number} has an outstanding balance of ₹{ticket.balance_due:.2f}. Balance must be zero or manager override provided.",
            )

    update_data = payload.model_dump(exclude_unset=True)
    update_data.pop("manager_override", None)

    for field, val in update_data.items():
        setattr(ticket, field, val)

    await TicketService.recompute_ticket_totals(ticket)
    await TicketService.check_threshold_pause(ticket)

    # If delivered or completed, consume parts
    if ticket.status in ["delivered", "completed"]:
        await TicketService.execute_stock_consumption_on_completion(db, ticket)

    # Status-Trigger Automation (e.g. Lathe Work -> Deliver core to lathe workshop)
    if "status" in update_data and update_data["status"]:
        try:
            from app.services.task_service import TaskService
            await TaskService.process_ticket_status_triggers(
                db=db,
                ticket=ticket,
                new_status=update_data["status"],
            )
            if update_data["status"].lower() == "delivered":
                from app.services.automation_service import AutomationService
                await AutomationService.schedule_ticket_delivery_automations(db, ticket)
        except Exception as e:
            print(f"Status trigger task creation exception: {e}")

    await db.commit()
    reloaded = await TicketService.get_ticket_with_relations(db, id)
    return _serialize_ticket(reloaded)


# 6. Parts Management: Add Part
@router.post("/{id}/parts", response_model=TicketPartResponse)
async def add_ticket_part(
    id: str,
    payload: TicketPartCreate,
    db: AsyncSession = Depends(get_db),
):
    ticket = await TicketService.get_ticket_with_relations(db, id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    part = await TicketService.add_part(
        session=db,
        ticket=ticket,
        inventory_item_id=payload.inventory_item_id,
        quantity=payload.quantity,
        unit_price=payload.unit_price,
        tax_rate=payload.tax_rate,
        notes=payload.notes,
    )
    await db.commit()

    part_reloaded = (
        await db.execute(
            select(TicketPart)
            .where(TicketPart.id == part.id)
            .options(selectinload(TicketPart.item))
        )
    ).scalar_one()

    return TicketPartResponse(
        id=part_reloaded.id,
        ticket_id=part_reloaded.ticket_id,
        inventory_item_id=part_reloaded.inventory_item_id,
        item_name=part_reloaded.item.name if part_reloaded.item else None,
        item_sku=part_reloaded.item.sku if part_reloaded.item else None,
        quantity=part_reloaded.quantity,
        unit_cost=part_reloaded.unit_cost,
        unit_price=part_reloaded.unit_price,
        tax_rate=part_reloaded.tax_rate,
        total_price=part_reloaded.total_price,
        is_reserved=part_reloaded.is_reserved,
        reservation_id=part_reloaded.reservation_id,
        is_consumed=part_reloaded.is_consumed,
        consumed_at=part_reloaded.consumed_at,
        notes=part_reloaded.notes,
        created_at=part_reloaded.created_at,
    )


# 7. Delete Part
@router.delete("/{id}/parts/{part_id}")
async def delete_ticket_part(
    id: str,
    part_id: str,
    db: AsyncSession = Depends(get_db),
):
    ticket = await TicketService.get_ticket_with_relations(db, id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    part_res = await db.execute(
        select(TicketPart).where(and_(TicketPart.id == part_id, TicketPart.ticket_id == id))
    )
    part = part_res.scalar_one_or_none()
    if not part:
        raise HTTPException(status_code=404, detail="Ticket part not found")

    # Release reservation if active
    if part.reservation_id:
        res_obj = await db.get(StockReservation, part.reservation_id)
        if res_obj and res_obj.status == "active":
            res_obj.status = "released"

    await db.delete(part)
    ticket.parts = [p for p in ticket.parts if p.id != part_id]
    await TicketService.recompute_ticket_totals(ticket)
    await db.commit()

    return {"message": "Part removed and stock reservation released successfully"}


# 8. Labor Management: Add Labor
@router.post("/{id}/labor", response_model=TicketLaborResponse)
async def add_ticket_labor(
    id: str,
    payload: TicketLaborCreate,
    db: AsyncSession = Depends(get_db),
):
    ticket = await TicketService.get_ticket_with_relations(db, id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    labor = await TicketService.add_labor(
        session=db,
        ticket=ticket,
        name=payload.name,
        labor_price=payload.labor_price,
        service_catalog_item_id=payload.service_catalog_item_id,
        sac_code=payload.sac_code or "9987",
        tax_rate=payload.tax_rate or 18.0,
        commission_rate=payload.commission_rate or 0.0,
        assigned_tech_id=payload.assigned_tech_id,
        duration_minutes=payload.duration_minutes or 30,
    )
    await db.commit()

    labor_reloaded = (
        await db.execute(
            select(TicketLabor)
            .where(TicketLabor.id == labor.id)
            .options(selectinload(TicketLabor.assigned_tech))
        )
    ).scalar_one()

    return TicketLaborResponse(
        id=labor_reloaded.id,
        ticket_id=labor_reloaded.ticket_id,
        service_catalog_item_id=labor_reloaded.service_catalog_item_id,
        name=labor_reloaded.name,
        sac_code=labor_reloaded.sac_code,
        labor_price=labor_reloaded.labor_price,
        tax_rate=labor_reloaded.tax_rate,
        total_price=labor_reloaded.total_price,
        commission_rate=labor_reloaded.commission_rate,
        commission_amount=labor_reloaded.commission_amount,
        assigned_tech_id=labor_reloaded.assigned_tech_id,
        assigned_tech_name=labor_reloaded.assigned_tech.full_name if labor_reloaded.assigned_tech else None,
        duration_minutes=labor_reloaded.duration_minutes,
        status=labor_reloaded.status,
        completed_at=labor_reloaded.completed_at,
        created_at=labor_reloaded.created_at,
    )


# 9. Delete Labor
@router.delete("/{id}/labor/{labor_id}")
async def delete_ticket_labor(
    id: str,
    labor_id: str,
    db: AsyncSession = Depends(get_db),
):
    ticket = await TicketService.get_ticket_with_relations(db, id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    labor = await db.get(TicketLabor, labor_id)
    if not labor or labor.ticket_id != id:
        raise HTTPException(status_code=404, detail="Labor item not found")

    await db.delete(labor)
    ticket.labor_items = [l for l in ticket.labor_items if l.id != labor_id]
    await TicketService.recompute_ticket_totals(ticket)
    await db.commit()

    return {"message": "Labor item removed successfully"}


# 10. Media Management
@router.post("/{id}/media", response_model=TicketMediaResponse)
async def add_ticket_media(
    id: str,
    payload: TicketMediaCreate,
    db: AsyncSession = Depends(get_db),
):
    ticket = await db.get(Ticket, id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    media = TicketMedia(
        ticket_id=id,
        media_type=payload.media_type,
        file_url=payload.file_url,
        file_name=payload.file_name,
        file_size_kb=payload.file_size_kb or 0,
        notes=payload.notes,
    )
    db.add(media)
    await db.commit()
    await db.refresh(media)
    return TicketMediaResponse.model_validate(media)


@router.get("/{id}/media", response_model=List[TicketMediaResponse])
async def list_ticket_media(
    id: str,
    db: AsyncSession = Depends(get_db),
):
    media_items = (
        await db.execute(
            select(TicketMedia).where(TicketMedia.ticket_id == id).order_by(TicketMedia.created_at.desc())
        )
    ).scalars().all()
    return [TicketMediaResponse.model_validate(m) for m in media_items]


# 11. Estimates: Generate & Tokenized Approval
@router.post("/{id}/estimates", response_model=TicketEstimateResponse)
async def create_ticket_estimate(
    id: str,
    payload: TicketEstimateCreate,
    db: AsyncSession = Depends(get_db),
):
    ticket = await TicketService.get_ticket_with_relations(db, id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    estimate = await TicketService.create_estimate(
        session=db,
        ticket=ticket,
        customer_notes=payload.customer_notes,
        custom_line_items=payload.line_items,
    )
    await db.commit()
    return TicketEstimateResponse.model_validate(estimate)


@router.post("/estimates/{token}/approve", response_model=TicketEstimateResponse)
async def process_estimate_approval(
    token: str,
    payload: EstimateApprovalPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    customer_ip = request.client.host if request.client else "unknown"
    estimate = await TicketService.approve_or_reject_estimate(
        session=db,
        token=token,
        action=payload.action,
        customer_ip=customer_ip,
        rejection_reason=payload.rejection_reason,
    )
    await db.commit()
    return TicketEstimateResponse.model_validate(estimate)


# 12. Subcontract Task Management
@router.post("/{id}/subcontract", response_model=TicketSubcontractResponse)
async def create_ticket_subcontract(
    id: str,
    payload: TicketSubcontractCreate,
    db: AsyncSession = Depends(get_db),
):
    ticket = await db.get(Ticket, id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    subcontract = TicketSubcontract(
        ticket_id=id,
        vendor_name=payload.vendor_name,
        vendor_phone=payload.vendor_phone,
        task_description=payload.task_description,
        cost=payload.cost,
        charged_to_customer=payload.charged_to_customer,
        expected_return_date=payload.expected_return_date,
        dispatch_date=utc_now(),
        notes=payload.notes,
        status="dispatched",
    )
    db.add(subcontract)
    await db.commit()
    await db.refresh(subcontract)
    return TicketSubcontractResponse.model_validate(subcontract)


@router.put("/subcontract/{subcontract_id}", response_model=TicketSubcontractResponse)
async def update_ticket_subcontract(
    subcontract_id: str,
    payload: TicketSubcontractUpdate,
    db: AsyncSession = Depends(get_db),
):
    sub = await db.get(TicketSubcontract, subcontract_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subcontract task not found")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(sub, k, v)

    if payload.status == "returned" and not sub.actual_return_date:
        sub.actual_return_date = utc_now()

    await db.commit()
    await db.refresh(sub)
    return TicketSubcontractResponse.model_validate(sub)


# 13. QA Checklist Update
@router.put("/{id}/qa-checklist", response_model=TicketResponse)
async def update_ticket_qa_checklist(
    id: str,
    payload: QAChecklistUpdate,
    db: AsyncSession = Depends(get_db),
):
    ticket = await TicketService.get_ticket_with_relations(db, id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket.qa_status = payload.qa_status
    ticket.qa_checklist = payload.qa_checklist
    await db.commit()

    reloaded = await TicketService.get_ticket_with_relations(db, id)
    return _serialize_ticket(reloaded)


# 14. Handover & Delivery Settlement
@router.post("/{id}/handover", response_model=TicketResponse)
async def handover_ticket(
    id: str,
    payload: TicketHandoverPayload,
    db: AsyncSession = Depends(get_db),
):
    ticket = await TicketService.get_ticket_with_relations(db, id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    await TicketService.process_handover(
        session=db,
        ticket=ticket,
        recipient=payload.handover_recipient,
        payment_method=payload.payment_method,
        payment_amount=payload.payment_amount,
        signature=payload.handover_signature,
        manager_override=payload.manager_override,
        notes=payload.notes,
    )
    from app.services.automation_service import AutomationService
    await AutomationService.schedule_ticket_delivery_automations(db, ticket)
    await db.commit()

    reloaded = await TicketService.get_ticket_with_relations(db, id)
    return _serialize_ticket(reloaded)


# 15. Printable Intake Slip & Barcode Payload
@router.get("/{id}/intake-slip")
async def get_intake_slip_data(
    id: str,
    db: AsyncSession = Depends(get_db),
):
    ticket = await TicketService.get_ticket_with_relations(db, id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    branch = ticket.branch
    client = ticket.client
    asset = ticket.asset

    return {
        "slip_type": "intake_receipt",
        "ticket_number": ticket.ticket_number,
        "barcode_code128": ticket.ticket_number,
        "tracking_url": f"/track/{ticket.tracking_token}",
        "branch": {
            "name": branch.name if branch else "Main Service Center",
            "phone": branch.phone if branch else "",
            "address": branch.address_line if branch else "",
            "city": branch.city if branch else "",
            "gstin": branch.gstin if branch else "",
        },
        "client": {
            "name": client.name if client else "",
            "phone": client.phone if client else "",
        },
        "asset": {
            "name": asset.name if asset else "Device",
            "brand": asset.brand if asset else "",
            "model": asset.model if asset else "",
            "identifier": asset.identifier if asset else "N/A",
            "warranty_status": asset.warranty_status if asset else "none",
        },
        "service": {
            "intake_date": ticket.created_at.strftime("%d-%b-%Y %I:%M %p"),
            "problem_reported": ticket.problem_reported,
            "promised_date": ticket.promised_delivery_date.strftime("%d-%b-%Y") if ticket.promised_delivery_date else "TBD",
            "advance_deposit": ticket.advance_deposit,
            "max_repair_budget": ticket.customer_max_repair_budget,
            "dynamic_fields": ticket.dynamic_fields,
        },
        "terms_and_conditions": [
            "Goods once left for repair are at owner's risk regarding data loss.",
            "Items not collected within 30 days of completion notice are subject to demurrage.",
            "Please produce this original slip or verify SMS token during handover.",
        ],
    }
