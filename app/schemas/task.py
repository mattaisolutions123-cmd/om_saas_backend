from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ==========================================
# Task Schemas
# ==========================================

class ChecklistItem(BaseModel):
    id: str
    text: str
    completed: bool = False


class TaskBase(BaseModel):
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    task_type: str = "manual"  # manual, auto-from-ticket-status, SLA-warning
    category: str = "General"  # Workshop, Procurement, Customer Communication, Lathe, Delivery, General, SLA Alert
    status: str = "Backlog"    # Backlog, In Progress, Review, Done, Cancelled
    priority: str = "standard" # low, standard, high, urgent
    sla_tier: Optional[str] = None  # T1, T2, T3
    deadline: Optional[datetime] = None
    pin_code: Optional[str] = None
    ticket_id: Optional[str] = None
    checklist: List[Dict[str, Any]] = []
    tags: List[str] = []
    task_metadata: Dict[str, Any] = {}


class TaskCreate(TaskBase):
    branch_id: Optional[str] = None
    author_id: Optional[str] = None
    executor_id: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    executor_id: Optional[str] = None
    sla_tier: Optional[str] = None
    deadline: Optional[datetime] = None
    pin_code: Optional[str] = None
    checklist: Optional[List[Dict[str, Any]]] = None
    tags: Optional[List[str]] = None
    task_metadata: Optional[Dict[str, Any]] = None
    completed_at: Optional[datetime] = None


class TaskReassignRequest(BaseModel):
    new_executor_id: str
    reason: Optional[str] = "Workload balancing / SLA reassignment"


class TaskResponse(TaskBase):
    id: str
    task_number: str
    branch_id: str
    author_id: str
    executor_id: Optional[str] = None
    sla_deadline: Optional[datetime] = None
    sla_status: str
    is_urgent: bool
    is_expired: bool
    overdue_minutes: int
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # Denormalized presentation fields
    author_name: Optional[str] = None
    executor_name: Optional[str] = None
    executor_email: Optional[str] = None
    ticket_number: Optional[str] = None
    client_name: Optional[str] = None
    client_phone: Optional[str] = None

    class Config:
        from_attributes = True


# ==========================================
# SLA Tier Config Schemas
# ==========================================

class SLATierConfigBase(BaseModel):
    tier_code: str  # T1, T2, T3
    name: str
    resolution_hours: float
    diagnosis_hours: float = 2.0
    warning_threshold_percent: float = 75.0
    l1_amber_hours_before: float = 4.0
    tech_penalty_points: float = 10.0
    customer_whatsapp_template: Optional[str] = None
    is_active: bool = True


class SLATierConfigCreate(SLATierConfigBase):
    branch_id: Optional[str] = None


class SLATierConfigUpdate(BaseModel):
    name: Optional[str] = None
    resolution_hours: Optional[float] = None
    diagnosis_hours: Optional[float] = None
    warning_threshold_percent: Optional[float] = None
    l1_amber_hours_before: Optional[float] = None
    tech_penalty_points: Optional[float] = None
    customer_whatsapp_template: Optional[str] = None
    is_active: Optional[bool] = None


class SLATierConfigResponse(SLATierConfigBase):
    id: str
    branch_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==========================================
# Escalation Log Schemas
# ==========================================

class EscalationLogResponse(BaseModel):
    id: str
    task_id: Optional[str] = None
    ticket_id: Optional[str] = None
    branch_id: str
    escalation_level: str
    severity: str
    message: str
    tech_id: Optional[str] = None
    penalty_applied: float
    acknowledged_by_manager: bool
    acknowledged_by_id: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    whatsapp_payload: Dict[str, Any] = {}
    created_at: datetime

    # Display fields
    tech_name: Optional[str] = None
    task_number: Optional[str] = None
    ticket_number: Optional[str] = None

    class Config:
        from_attributes = True


class EscalationAcknowledgeRequest(BaseModel):
    note: Optional[str] = None


# ==========================================
# Status Trigger Rule Schemas
# ==========================================

class StatusTriggerRuleBase(BaseModel):
    ticket_status_source: str  # "Lathe Work", "Spare Wait", "Work Done"
    task_title_template: str   # "Deliver core to lathe workshop", "Source part", "Notify client for pickup"
    task_category: str        # "Workshop", "Procurement", "Customer Communication"
    priority: str = "high"
    due_hours: float = 24.0
    role_target: str = "technician"
    is_active: bool = True


class StatusTriggerRuleCreate(StatusTriggerRuleBase):
    branch_id: Optional[str] = None


class StatusTriggerRuleResponse(StatusTriggerRuleBase):
    id: str
    branch_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==========================================
# Smart Workload Balancing Schemas
# ==========================================

class TechnicianWorkload(BaseModel):
    technician_id: str
    name: str
    email: str
    skills: List[str] = []
    matched_skills: List[str] = []
    open_tickets_count: int
    open_tasks_count: int
    tech_score: float
    workload_score: float
    is_recommended: bool = False


class WorkloadBalanceResponse(BaseModel):
    branch_id: str
    category: Optional[str] = None
    recommended_technician: Optional[TechnicianWorkload] = None
    technicians: List[TechnicianWorkload] = []


# ==========================================
# SLA Analytics Schemas
# ==========================================

class CategorySLAMetric(BaseModel):
    category: str
    total_tasks: int
    on_time_count: int
    breached_count: int
    on_time_percent: float


class TechnicianSLAMetric(BaseModel):
    technician_id: str
    technician_name: str
    total_assigned: int
    completed_count: int
    on_time_count: int
    breached_count: int
    on_time_percent: float
    tech_score: float
    penalties_incurred: float


class SLAAnalyticsResponse(BaseModel):
    branch_id: Optional[str] = None
    period_label: str
    total_tasks: int
    completed_tasks: int
    on_time_tasks: int
    breached_tasks: int
    overall_on_time_percent: float
    avg_turnaround_hours: float
    active_breaches_count: int
    active_urgent_count: int
    categories: List[CategorySLAMetric] = []
    technicians: List[TechnicianSLAMetric] = []
    tier_compliance: Dict[str, float] = {}
