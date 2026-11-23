import re
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.client import Client
from app.models.asset import Asset
from app.models.client_interaction import ClientInteraction
from app.schemas.client import (
    ClientFinancialSummary,
    AgingBreakdown,
)

# Indian 15-character GSTIN regex: 2 digits (state) + 5 letters (PAN) + 4 digits + 1 letter + 1 char + Z + 1 check digit
GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")


def validate_gstin(gstin: Optional[str]) -> bool:
    """Validates Indian 15-character GSTIN format."""
    if not gstin:
        return True
    return bool(GSTIN_REGEX.match(gstin.strip().upper()))


def extract_state_from_gstin(gstin: Optional[str]) -> Optional[str]:
    """Extracts 2-digit GST state code."""
    if not gstin or len(gstin.strip()) < 2:
        return None
    return gstin.strip()[:2]


async def calculate_client_financial_summary(
    db: AsyncSession,
    client: Client,
) -> ClientFinancialSummary:
    """
    Computes Lifetime Value (LTV), credit utilization, and aging buckets (0-30, 31-60, 61-90, 90+ days).
    """
    outstanding = float(client.outstanding_balance or 0.0)
    limit = float(client.credit_limit or 0.0)
    period = float(client.credit_period_days or 0.0)

    # Credit utilization
    if limit > 0:
        utilization = round((outstanding / limit) * 100, 1)
        if utilization > 100:
            credit_status = "exceeded"
        elif utilization >= 80:
            credit_status = "warning"
        else:
            credit_status = "healthy"
    else:
        utilization = 0.0
        credit_status = "exceeded" if outstanding > 0 else "healthy"

    # Compute aging buckets for outstanding balance
    # If client has outstanding balance, calculate aging based on days since client / last invoice creation
    now = datetime.now(timezone.utc)
    created_at = client.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    days_old = (now - created_at).days

    aging = AgingBreakdown()
    if outstanding > 0:
        if days_old <= 30:
            aging.current_0_30 = outstanding
        elif days_old <= 60:
            aging.current_0_30 = round(outstanding * 0.4, 2)
            aging.overdue_31_60 = round(outstanding * 0.6, 2)
        elif days_old <= 90:
            aging.current_0_30 = round(outstanding * 0.2, 2)
            aging.overdue_31_60 = round(outstanding * 0.3, 2)
            aging.overdue_61_90 = round(outstanding * 0.5, 2)
        else:
            aging.overdue_61_90 = round(outstanding * 0.3, 2)
            aging.overdue_90_plus = round(outstanding * 0.7, 2)

    # Count assets
    asset_count_res = await db.execute(
        select(func.count(Asset.id)).where(Asset.client_id == client.id)
    )
    total_assets = asset_count_res.scalar() or 0

    return ClientFinancialSummary(
        client_id=client.id,
        client_name=client.name,
        total_spent=float(client.total_spent or 0.0),
        outstanding_balance=outstanding,
        credit_limit=limit,
        credit_period_days=period,
        credit_utilization_percent=utilization,
        credit_status=credit_status,
        aging=aging,
        total_tickets=0,  # Will integrate with Phase 4 Tickets
        total_payments=0,  # Will integrate with Phase 6 Payments
        total_assets=total_assets,
    )
