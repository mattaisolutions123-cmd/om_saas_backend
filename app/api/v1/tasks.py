from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.task import Task, SLATierConfig, EscalationLog, StatusTriggerRule
from app.models.user import User
from app.models.branch import Branch
from app.models.ticket import Ticket
from app.schemas.task import (
    TaskCreate,
    TaskUpdate,
    TaskResponse,
    TaskReassignRequest,
    SLATierConfigCreate,
    SLATierConfigUpdate,
    SLATierConfigResponse,
    EscalationLogResponse,
    EscalationAcknowledgeRequest,
    StatusTriggerRuleCreate,
    StatusTriggerRuleResponse,
    WorkloadBalanceResponse,
    TechnicianWorkload,
    SLAAnalyticsResponse,
)
from app.services.task_service import TaskService
from app.services.task_websocket import task_ws_manager
from app.services.audit import log_audit_event

router = APIRouter(prefix="/tasks", tags=["Tasks & SLA Engine"])


# ==========================================
# 1. List Tasks
# ==========================================
@router.get("", response_model=List[TaskResponse])
async def list_tasks(
    branch_id: Optional[str] = Query(None),
    executor_id: Optional[str] = Query(None),
    author_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    sla_tier: Optional[str] = Query(None),
    pin_code: Optional[str] = Query(None),
    ticket_id: Optional[str] = Query(None),
    is_urgent: Optional[bool] = Query(None),
    is_expired: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Task)
        .options(
            selectinload(Task.author),
            selectinload(Task.executor),
            selectinload(Task.ticket).selectinload(Ticket.client),
            selectinload(Task.branch),
        )
        .order_by(Task.deadline.asc().nullslast(), Task.created_at.desc())
    )

    if branch_id:
        query = query.where(Task.branch_id == branch_id)
    if executor_id:
        query = query.where(Task.executor_id == executor_id)
    if author_id:
        query = query.where(Task.author_id == author_id)
    if status:
        query = query.where(Task.status.ilike(status))
    if category:
        query = query.where(Task.category.ilike(category))
    if priority:
        query = query.where(Task.priority == priority)
    if sla_tier:
        query = query.where(Task.sla_tier == sla_tier)
    if pin_code:
        query = query.where(Task.pin_code == pin_code)
    if ticket_id:
        query = query.where(Task.ticket_id == ticket_id)
    if is_urgent is not None:
        query = query.where(Task.is_urgent == is_urgent)
    if is_expired is not None:
        query = query.where(Task.is_expired == is_expired)
    if search:
        search_filter = or_(
            Task.title.ilike(f"%{search}%"),
            Task.description.ilike(f"%{search}%"),
            Task.task_number.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)

    tasks = (await db.execute(query)).scalars().all()
    return [TaskService.serialize_task(t) for t in tasks]


# ==========================================
# 2. Create Task (Manual)
# ==========================================
@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
):
    # Resolve Branch
    branch_id = payload.branch_id
    if not branch_id:
        branch_res = await db.execute(select(Branch).limit(1))
        branch = branch_res.scalar_one_or_none()
        if not branch:
            raise HTTPException(status_code=400, detail="No active branch found. Please specify branch_id.")
        branch_id = branch.id

    # Resolve Author
    author_id = payload.author_id
    if not author_id:
        user_res = await db.execute(select(User).limit(1))
        first_user = user_res.scalar_one_or_none()
        if not first_user:
            raise HTTPException(status_code=400, detail="No active users found.")
        author_id = first_user.id

    # Resolve Executor via Smart Workload Balancing if not manually selected
    executor_id = payload.executor_id
    if not executor_id:
        recommendations = await TaskService.calculate_workload_balance(
            db=db,
            branch_id=branch_id,
            category=payload.category,
        )
        if recommendations:
            executor_id = recommendations[0]["technician_id"]

    # Calculate SLA Deadline if tier provided
    now = datetime.now(timezone.utc)
    sla_deadline = payload.deadline
    if payload.sla_tier and not payload.deadline:
        tier_cfg = (await db.execute(
            select(SLATierConfig).where(SLATierConfig.tier_code == payload.sla_tier)
        )).scalar_one_or_none()
        if tier_cfg:
            from datetime import timedelta
            sla_deadline = now + timedelta(hours=tier_cfg.resolution_hours)

    task_number = await TaskService.generate_task_number(db, branch_id)

    task = Task(
        task_number=task_number,
        branch_id=branch_id,
        title=payload.title,
        description=payload.description,
        task_type=payload.task_type or "manual",
        author_id=author_id,
        executor_id=executor_id,
        category=payload.category or "General",
        status=payload.status or "Backlog",
        priority=payload.priority or "standard",
        sla_tier=payload.sla_tier,
        deadline=payload.deadline or sla_deadline,
        sla_deadline=sla_deadline,
        pin_code=payload.pin_code,
        ticket_id=payload.ticket_id,
        checklist=payload.checklist or [],
        tags=payload.tags or [],
        task_metadata=payload.task_metadata or {},
    )
    db.add(task)
    await db.commit()

    reloaded = await TaskService.get_task_with_relations(db, task.id)
    serialized = TaskService.serialize_task(reloaded)

    # Real-time WebSocket Broadcast
    await task_ws_manager.broadcast_task_event("task_created", serialized, branch_id)

    await log_audit_event(
        db=db,
        action="create_task",
        entity="task",
        entity_id=task.id,
        before_state=None,
        after_state={"task_number": task_number, "title": task.title},
    )

    return serialized


# ==========================================
# 3. Get Task Detail
# ==========================================
@router.get("/{id}", response_model=TaskResponse)
async def get_task(
    id: str,
    db: AsyncSession = Depends(get_db),
):
    task = await TaskService.get_task_with_relations(db, id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskService.serialize_task(task)


# ==========================================
# 4. Update Task (Status Drag-Drop, Checklist, etc.)
# ==========================================
@router.put("/{id}", response_model=TaskResponse)
async def update_task(
    id: str,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
):
    task = await TaskService.get_task_with_relations(db, id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    old_status = task.status
    update_data = payload.model_dump(exclude_unset=True)

    # Handle completion timestamp
    if "status" in update_data:
        new_status = update_data["status"]
        if new_status.lower() in ["done", "completed"] and old_status.lower() not in ["done", "completed"]:
            task.completed_at = datetime.now(timezone.utc)
            task.is_urgent = False
            task.is_expired = False
        elif new_status.lower() not in ["done", "completed"]:
            task.completed_at = None

    for field, val in update_data.items():
        setattr(task, field, val)

    await db.commit()

    reloaded = await TaskService.get_task_with_relations(db, id)
    serialized = TaskService.serialize_task(reloaded)

    # WebSocket Broadcast event (moved or updated)
    event_type = "task_moved" if "status" in update_data and old_status != update_data["status"] else "task_updated"
    await task_ws_manager.broadcast_task_event(event_type, serialized, task.branch_id)

    return serialized


# ==========================================
# 5. Delete Task
# ==========================================
@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    id: str,
    db: AsyncSession = Depends(get_db),
):
    task = await db.get(Task, id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    branch_id = task.branch_id
    task_num = task.task_number
    await db.delete(task)
    await db.commit()

    await task_ws_manager.broadcast_task_event("task_deleted", {"id": id, "task_number": task_num}, branch_id)
    return None


# ==========================================
# 6. Reassign Task (1-Click Reassignment)
# ==========================================
@router.post("/{id}/reassign", response_model=TaskResponse)
async def reassign_task(
    id: str,
    payload: TaskReassignRequest,
    db: AsyncSession = Depends(get_db),
):
    task = await TaskService.get_task_with_relations(db, id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    new_tech = await db.get(User, payload.new_executor_id)
    if not new_tech:
        raise HTTPException(status_code=404, detail="New executor user not found")

    old_executor_name = task.executor.full_name if task.executor else "Unassigned"
    task.executor_id = payload.new_executor_id

    # Append to reassign history in metadata
    meta = dict(task.task_metadata or {})
    history = meta.get("reassign_history", [])
    history.append({
        "from": old_executor_name,
        "to": new_tech.full_name,
        "reason": payload.reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    meta["reassign_history"] = history
    task.task_metadata = meta

    # Reset breach flag if actively reassigned under emergency manager intervention
    if task.is_expired:
        task.is_expired = False
        task.is_urgent = True
        task.priority = "urgent"

    await db.commit()

    reloaded = await TaskService.get_task_with_relations(db, id)
    serialized = TaskService.serialize_task(reloaded)

    await task_ws_manager.broadcast_task_event("task_reassigned", serialized, task.branch_id)
    return serialized


# ==========================================
# 7. Smart Workload Balancing Endpoint
# ==========================================
@router.get("/workload/balance", response_model=WorkloadBalanceResponse)
async def get_workload_balance(
    branch_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    required_skills: Optional[str] = Query(None),  # Comma separated
    db: AsyncSession = Depends(get_db),
):
    if not branch_id:
        b_res = await db.execute(select(Branch).limit(1))
        b = b_res.scalar_one_or_none()
        branch_id = b.id if b else "default"

    skills_list = [s.strip() for s in required_skills.split(",")] if required_skills else []
    technicians = await TaskService.calculate_workload_balance(
        db=db,
        branch_id=branch_id,
        category=category,
        required_skills=skills_list,
    )

    recommended = next((t for t in technicians if t.get("is_recommended")), None)
    return WorkloadBalanceResponse(
        branch_id=branch_id,
        category=category,
        recommended_technician=recommended,
        technicians=technicians,
    )


# ==========================================
# 8. SLA Tier Configuration Endpoints
# ==========================================
@router.get("/sla/tiers", response_model=List[SLATierConfigResponse])
async def list_sla_tiers(
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    await TaskService.seed_defaults(db, branch_id)
    query = select(SLATierConfig).order_by(SLATierConfig.resolution_hours.asc())
    if branch_id:
        query = query.where(or_(SLATierConfig.branch_id == branch_id, SLATierConfig.branch_id.is_(None)))
    tiers = (await db.execute(query)).scalars().all()
    return tiers


@router.put("/sla/tiers/{id}", response_model=SLATierConfigResponse)
async def update_sla_tier(
    id: str,
    payload: SLATierConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    tier = await db.get(SLATierConfig, id)
    if not tier:
        raise HTTPException(status_code=404, detail="SLA Tier configuration not found")

    for field, val in payload.model_dump(exclude_unset=True).items():
        setattr(tier, field, val)

    await db.commit()
    await db.refresh(tier)
    return tier


# ==========================================
# 9. SLA Scheduler & Escalation Job Trigger
# ==========================================
@router.post("/sla/check-escalations")
async def trigger_sla_escalations(
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Evaluates 75% Elapsed, L1 Amber Push, L2 Breach, L3 Courtesy WhatsApp, and L4 Analytics.
    """
    summary = await TaskService.run_sla_escalation_engine(db, branch_id)
    return {
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
    }


# ==========================================
# 10. Escalation Logs
# ==========================================
@router.get("/sla/logs", response_model=List[EscalationLogResponse])
async def list_escalation_logs(
    branch_id: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    unacknowledged_only: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(EscalationLog)
        .options(
            selectinload(EscalationLog.task),
            selectinload(EscalationLog.ticket),
            selectinload(EscalationLog.tech),
        )
        .order_by(EscalationLog.created_at.desc())
        .limit(limit)
    )
    if branch_id:
        query = query.where(EscalationLog.branch_id == branch_id)
    if level:
        query = query.where(EscalationLog.escalation_level == level)
    if severity:
        query = query.where(EscalationLog.severity == severity)
    if unacknowledged_only:
        query = query.where(EscalationLog.acknowledged_by_manager == False)

    logs = (await db.execute(query)).scalars().all()
    results = []
    for l in logs:
        results.append(
            EscalationLogResponse(
                id=l.id,
                task_id=l.task_id,
                ticket_id=l.ticket_id,
                branch_id=l.branch_id,
                escalation_level=l.escalation_level,
                severity=l.severity,
                message=l.message,
                tech_id=l.tech_id,
                penalty_applied=l.penalty_applied,
                acknowledged_by_manager=l.acknowledged_by_manager,
                acknowledged_by_id=l.acknowledged_by_id,
                acknowledged_at=l.acknowledged_at,
                whatsapp_payload=l.whatsapp_payload or {},
                created_at=l.created_at,
                tech_name=l.tech.full_name if l.tech else None,
                task_number=l.task.task_number if l.task else None,
                ticket_number=l.ticket.ticket_number if l.ticket else None,
            )
        )
    return results


@router.post("/sla/logs/{id}/acknowledge", response_model=EscalationLogResponse)
async def acknowledge_escalation_log(
    id: str,
    payload: EscalationAcknowledgeRequest,
    db: AsyncSession = Depends(get_db),
):
    log_entry = await db.get(EscalationLog, id)
    if not log_entry:
        raise HTTPException(status_code=404, detail="Escalation log not found")

    log_entry.acknowledged_by_manager = True
    log_entry.acknowledged_at = datetime.now(timezone.utc)
    await db.commit()

    return await list_escalation_logs(branch_id=log_entry.branch_id, limit=1, db=db)


# ==========================================
# 11. SLA Analytics (L4)
# ==========================================
@router.get("/sla/analytics", response_model=SLAAnalyticsResponse)
async def get_sla_analytics(
    branch_id: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await TaskService.get_sla_analytics(db, branch_id=branch_id, year=year, month=month)


# ==========================================
# 12. Status-Trigger Rules
# ==========================================
@router.get("/rules/status-triggers", response_model=List[StatusTriggerRuleResponse])
async def list_status_trigger_rules(
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    await TaskService.seed_defaults(db, branch_id)
    query = select(StatusTriggerRule).order_by(StatusTriggerRule.created_at.asc())
    if branch_id:
        query = query.where(or_(StatusTriggerRule.branch_id == branch_id, StatusTriggerRule.branch_id.is_(None)))
    return (await db.execute(query)).scalars().all()


@router.post("/rules/status-triggers", response_model=StatusTriggerRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_status_trigger_rule(
    payload: StatusTriggerRuleCreate,
    db: AsyncSession = Depends(get_db),
):
    rule = StatusTriggerRule(**payload.model_dump())
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


# ==========================================
# 13. WebSocket for Real-time Board Sync
# ==========================================
@router.websocket("/ws")
async def websocket_task_endpoint(websocket: WebSocket, branch_id: str = "default"):
    await task_ws_manager.connect(websocket, branch_id)
    try:
        while True:
            # Receive client ping or event
            data = await websocket.receive_text()
            # Echo or broadcast client actions if needed
            await websocket.send_text(f'{{"type":"pong","received":{data}}}')
    except WebSocketDisconnect:
        task_ws_manager.disconnect(websocket, branch_id)
    except Exception:
        task_ws_manager.disconnect(websocket, branch_id)
