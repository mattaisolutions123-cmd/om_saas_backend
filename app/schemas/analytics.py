from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class KPICardItem(BaseModel):
    key: str
    label: str
    value: float
    formatted_value: str
    change_percent: float = 0.0
    change_direction: str = "up"  # up, down, neutral
    description: Optional[str] = None
    category: str = "financial"  # financial, operations, inventory, compliance


class TicketVelocityStats(BaseModel):
    intake_count: int
    completed_count: int
    velocity_ratio: float  # completed / intake
    avg_turnaround_hours: float
    active_in_progress: int


class InventoryTurnoverStats(BaseModel):
    total_inventory_valuation: float
    total_parts_consumed_cost: float
    turnover_ratio: float
    days_inventory_on_hand: float
    low_stock_alert_count: int


class CompanySummaryResponse(BaseModel):
    scope: str  # global, branch, technician
    branch_id: Optional[str] = None
    branch_name: Optional[str] = None
    role: str
    date_range_label: str
    currency: str = "INR"

    # Core Aggregations
    total_revenue: float
    total_order_profit: float
    order_profit_margin_percent: float
    total_sales_margin_percent: float
    total_staff_commission: float
    total_stock_valuation: float

    # Sub-system metrics
    ticket_velocity: TicketVelocityStats
    inventory_turnover: InventoryTurnoverStats
    minimum_balance_breaches: int

    # Executive KPI Cards
    kpi_cards: List[KPICardItem]


class TimeSeriesPoint(BaseModel):
    date: str  # YYYY-MM-DD
    revenue: float = 0.0
    expenses: float = 0.0
    profit: float = 0.0
    tickets_intake: int = 0
    tickets_completed: int = 0


class BranchCompareItem(BaseModel):
    branch_id: str
    branch_name: str
    branch_code: str
    revenue: float
    profit: float
    margin_percent: float
    tickets_count: int
    sla_on_time_percent: float


class TrendsResponse(BaseModel):
    scope: str
    date_from: str
    date_to: str
    time_series: List[TimeSeriesPoint]
    branch_comparison: List[BranchCompareItem]
    revenue_by_category: List[Dict[str, Any]]
    payment_methods_share: List[Dict[str, Any]]
