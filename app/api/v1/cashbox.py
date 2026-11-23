from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc

from app.db.session import get_db
from app.api.v1.auth import get_current_user
from app.models.user import User
from app.models.cashbox import (
    CashRegisterShift,
    Account,
    LedgerEntry,
    Expense,
    Refund,
    CommissionRule,
    TechnicianCommission,
)
from app.schemas.cashbox import (
    CashRegisterShiftOpen,
    CashRegisterShiftClose,
    CashRegisterShiftResponse,
    AccountCreate,
    AccountResponse,
    LedgerEntryResponse,
    ExpenseCreate,
    ExpenseResponse,
    RefundCreate,
    RefundResponse,
    CommissionRuleCreate,
    CommissionRuleResponse,
    PayrollReportResponse,
    ProfitPerTicketResponse,
    ConsolidatedFinancialsResponse,
    UpiWebhookPayload,
    UpiWebhookResponse,
)
from app.services.cashbox_service import CashboxService

router = APIRouter(prefix="/cashbox", tags=["Cashbox & Payments Engine"])


# 1. Shifts & Blind Closeout
@router.post("/shifts/open", response_model=CashRegisterShiftResponse, status_code=status.HTTP_201_CREATED)
async def open_shift(
    payload: CashRegisterShiftOpen,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await CashboxService.open_shift(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/shifts/{id}/close", response_model=CashRegisterShiftResponse)
async def close_shift(
    id: str,
    payload: CashRegisterShiftClose,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await CashboxService.blind_closeout_shift(db, id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/shifts/active", response_model=Optional[CashRegisterShiftResponse])
async def get_active_shift(
    branch_id: Optional[str] = Query(None),
    cashier_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(CashRegisterShift).where(CashRegisterShift.status == "OPEN")
    if branch_id:
        query = query.where(CashRegisterShift.branch_id == branch_id)
    if cashier_id:
        query = query.where(CashRegisterShift.cashier_id == cashier_id)
    else:
        query = query.where(CashRegisterShift.cashier_id == current_user.id)

    res = await db.execute(query.order_by(desc(CashRegisterShift.opened_at)).limit(1))
    return res.scalar_one_or_none()


@router.get("/shifts", response_model=List[CashRegisterShiftResponse])
async def list_shifts(
    branch_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(CashRegisterShift)
    if branch_id:
        query = query.where(CashRegisterShift.branch_id == branch_id)
    if status_filter:
        query = query.where(CashRegisterShift.status == status_filter)
    query = query.order_by(desc(CashRegisterShift.opened_at)).limit(50)
    res = await db.execute(query)
    return res.scalars().all()


@router.get("/shifts/{id}", response_model=CashRegisterShiftResponse)
async def get_shift_detail(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(CashRegisterShift).where(CashRegisterShift.id == id)
    res = await db.execute(stmt)
    shift = res.scalar_one_or_none()
    if not shift:
        raise HTTPException(status_code=404, detail="Cash register shift not found")
    return shift


# 2. Accounts (Chart of Accounts)
@router.get("/accounts", response_model=List[AccountResponse])
async def list_accounts(
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_branch = branch_id or current_user.branch_id or "branch-main"
    # Ensure default accounts exist
    await CashboxService.get_or_create_default_accounts(db, target_branch)
    await db.commit()

    query = select(Account).where(
        or_(Account.branch_id == target_branch, Account.branch_id == None)
    ).order_by(Account.code.asc())
    res = await db.execute(query)
    return res.scalars().all()


# 3. Double-Entry General Ledger
@router.get("/ledger", response_model=List[LedgerEntryResponse])
async def list_ledger_entries(
    branch_id: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
    reference_type: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(LedgerEntry)
    if branch_id:
        query = query.where(LedgerEntry.branch_id == branch_id)
    if account_id:
        query = query.where(LedgerEntry.account_id == account_id)
    if reference_type:
        query = query.where(LedgerEntry.reference_type == reference_type)

    query = query.order_by(desc(LedgerEntry.entry_date)).limit(limit)
    res = await db.execute(query)
    return res.scalars().all()


# 4. Expenses & Vouchers
@router.post("/expenses", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
async def create_expense(
    payload: ExpenseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await CashboxService.create_expense(db, payload, current_user.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/expenses", response_model=List[ExpenseResponse])
async def list_expenses(
    branch_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    ticket_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Expense)
    if branch_id:
        query = query.where(Expense.branch_id == branch_id)
    if category:
        query = query.where(Expense.category == category)
    if ticket_id:
        query = query.where(Expense.ticket_id == ticket_id)

    query = query.order_by(desc(Expense.created_at)).limit(100)
    res = await db.execute(query)
    return res.scalars().all()


# 5. Refunds
@router.post("/refunds", response_model=RefundResponse, status_code=status.HTTP_201_CREATED)
async def create_refund(
    payload: RefundCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await CashboxService.create_refund(db, payload, current_user.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/refunds", response_model=List[RefundResponse])
async def list_refunds(
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Refund)
    if branch_id:
        query = query.where(Refund.branch_id == branch_id)
    query = query.order_by(desc(Refund.created_at)).limit(100)
    res = await db.execute(query)
    return res.scalars().all()


# 6. Ticket Profitability
@router.get("/profitability/ticket/{id}", response_model=ProfitPerTicketResponse)
async def get_ticket_profitability(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await CashboxService.calculate_ticket_profitability(db, id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# 7. Commission Rules & Payroll
@router.get("/commissions/rules", response_model=List[CommissionRuleResponse])
async def list_commission_rules(
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(CommissionRule)
    if branch_id:
        query = query.where(or_(CommissionRule.branch_id == branch_id, CommissionRule.branch_id == None))
    res = await db.execute(query)
    return res.scalars().all()


@router.post("/commissions/rules", response_model=CommissionRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_commission_rule(
    payload: CommissionRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rule = CommissionRule(
        branch_id=payload.branch_id,
        name=payload.name,
        role=payload.role,
        technician_id=payload.technician_id,
        rule_type=payload.rule_type,
        flat_amount=payload.flat_amount,
        labor_percentage=payload.labor_percentage,
        tiers_config=payload.tiers_config,
        is_active=payload.is_active,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.get("/payroll", response_model=PayrollReportResponse)
async def get_payroll_report(
    month: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now = datetime.now()
    m = month or now.month
    y = year or now.year
    return await CashboxService.compute_payroll_report(db, m, y, branch_id)


# 8. Multi-branch Consolidation
@router.get("/consolidation", response_model=ConsolidatedFinancialsResponse)
async def get_consolidated_financials(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await CashboxService.get_consolidated_financials(db)


# 9. Real-time UPI Webhook Handler
@router.post("/webhook/upi", response_model=UpiWebhookResponse)
async def handle_upi_webhook(
    payload: UpiWebhookPayload,
    db: AsyncSession = Depends(get_db),
):
    """
    Public webhook receiver for UPI QR gateway callbacks.
    """
    try:
        return await CashboxService.handle_upi_webhook(db, payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
