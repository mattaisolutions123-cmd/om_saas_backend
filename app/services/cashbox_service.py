import secrets
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func

from app.models.cashbox import (
    CashRegisterShift,
    Account,
    LedgerEntry,
    Expense,
    Refund,
    CommissionRule,
    TechnicianCommission,
)
from app.models.sales import Payment, Sale, Invoice
from app.models.ticket import Ticket, TicketPart, TicketLabor
from app.models.branch import Branch
from app.models.user import User
from app.models.inventory import InventoryItem
from app.services.inventory_service import InventoryService
from app.schemas.cashbox import (
    CashRegisterShiftOpen,
    CashRegisterShiftClose,
    ExpenseCreate,
    RefundCreate,
    CommissionRuleCreate,
    ProfitPerTicketResponse,
    BranchFinancialSummary,
    ConsolidatedFinancialsResponse,
    PayrollReportItem,
    PayrollReportResponse,
    UpiWebhookPayload,
    UpiWebhookResponse,
)


class CashboxService:
    @staticmethod
    def _utc_now():
        return datetime.now(timezone.utc)

    @staticmethod
    async def get_or_create_default_accounts(db: AsyncSession, branch_id: str) -> Dict[str, Account]:
        """
        Ensures standard chart of accounts exists for the branch.
        """
        defaults = [
            ("1010_CASH", "Cash in Register", "asset"),
            ("1020_UPI", "UPI Digital Settlement", "asset"),
            ("1030_CARD", "POS Card Settlement", "asset"),
            ("1040_AR", "Accounts Receivable", "asset"),
            ("3010_EQUITY_FLOAT", "Opening Cash Float Equity", "equity"),
            ("4010_SALES", "Sales & Service Revenue", "revenue"),
            ("5010_EXP_SUBCONTRACT", "Subcontractor Lathe/Repair Expense", "expense"),
            ("5020_EXP_SPARE", "Spare Parts Cash Purchase", "expense"),
            ("5030_EXP_COMMISSION", "Technician Commissions", "expense"),
            ("5090_EXP_GENERAL", "General Store & Daily Expense", "expense"),
        ]

        accounts_map: Dict[str, Account] = {}
        for code, name, acc_type in defaults:
            stmt = select(Account).where(
                and_(
                    Account.branch_id == branch_id,
                    Account.code == code,
                )
            )
            res = await db.execute(stmt)
            acc = res.scalar_one_or_none()
            if not acc:
                acc = Account(
                    account_number=f"ACC-{branch_id[:6].upper()}-{code}",
                    branch_id=branch_id,
                    code=code,
                    name=name,
                    type=acc_type,
                    currency="INR",
                    balance=0.0,
                    is_active=True,
                )
                db.add(acc)
                await db.flush()
            accounts_map[code] = acc

        return accounts_map

    @staticmethod
    async def record_double_entry(
        db: AsyncSession,
        branch_id: str,
        shift_id: Optional[str],
        reference_type: str,
        reference_id: Optional[str],
        entries: List[Dict[str, Any]],  # [{"account_id": ..., "debit": ..., "credit": ..., "narration": ...}]
    ) -> str:
        """
        Enforces double-entry equation: Total Debits == Total Credits.
        Updates running account balances.
        """
        total_debits = sum(round(e.get("debit", 0.0), 2) for e in entries)
        total_credits = sum(round(e.get("credit", 0.0), 2) for e in entries)

        if abs(total_debits - total_credits) > 0.01:
            raise ValueError(
                f"Double-entry ledger unbalanced! Total Debits (₹{total_debits:.2f}) != Total Credits (₹{total_credits:.2f})"
            )

        group_id = secrets.token_hex(16)
        now = CashboxService._utc_now()

        for entry in entries:
            acc_id = entry["account_id"]
            debit_val = round(entry.get("debit", 0.0), 2)
            credit_val = round(entry.get("credit", 0.0), 2)
            narration = entry.get("narration", reference_type)

            le = LedgerEntry(
                transaction_group_id=group_id,
                branch_id=branch_id,
                shift_id=shift_id,
                account_id=acc_id,
                reference_type=reference_type,
                reference_id=reference_id,
                debit=debit_val,
                credit=credit_val,
                entry_date=now,
                narration=narration,
            )
            db.add(le)

            # Update account balance
            acc_stmt = select(Account).where(Account.id == acc_id)
            acc_res = await db.execute(acc_stmt)
            account = acc_res.scalar_one_or_none()
            if account:
                if account.type in ["asset", "expense"]:
                    account.balance += (debit_val - credit_val)
                else:  # liability, equity, revenue
                    account.balance += (credit_val - debit_val)

        await db.flush()
        return group_id

    @staticmethod
    async def open_shift(db: AsyncSession, payload: CashRegisterShiftOpen) -> CashRegisterShift:
        """
        Opens a new cash register shift with cashier binding and float denominations.
        """
        # Ensure default accounts
        accounts = await CashboxService.get_or_create_default_accounts(db, payload.branch_id)

        # Check existing open shift for this cashier or branch
        existing = await db.execute(
            select(CashRegisterShift).where(
                and_(
                    CashRegisterShift.branch_id == payload.branch_id,
                    CashRegisterShift.cashier_id == payload.cashier_id,
                    CashRegisterShift.status == "OPEN",
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Cashier already has an active OPEN register shift.")

        now = CashboxService._utc_now()
        shift_num = f"SHIFT-{now.strftime('%Y%m')}-{secrets.token_hex(4).upper()}"

        shift = CashRegisterShift(
            shift_number=shift_num,
            branch_id=payload.branch_id,
            cashier_id=payload.cashier_id,
            status="OPEN",
            opened_at=now,
            opening_float=payload.opening_float,
            opening_denominations=payload.opening_denominations,
            closing_denominations={},
            closing_counted_cash=0.0,
            expected_cash=0.0,
            variance=0.0,
            is_balanced=True,
            notes=payload.notes,
            audit_meta={"opened_by_user_id": payload.cashier_id},
        )
        db.add(shift)
        await db.flush()

        # Double-entry for opening float if > 0
        if payload.opening_float > 0:
            cash_acc = accounts["1010_CASH"]
            float_acc = accounts["3010_EQUITY_FLOAT"]
            await CashboxService.record_double_entry(
                db=db,
                branch_id=payload.branch_id,
                shift_id=shift.id,
                reference_type="SHIFT_OPEN",
                reference_id=shift.id,
                entries=[
                    {
                        "account_id": cash_acc.id,
                        "debit": payload.opening_float,
                        "credit": 0.0,
                        "narration": f"Opening cash float for {shift.shift_number}",
                    },
                    {
                        "account_id": float_acc.id,
                        "debit": 0.0,
                        "credit": payload.opening_float,
                        "narration": f"Float capital provision for {shift.shift_number}",
                    },
                ],
            )

        await db.commit()
        await db.refresh(shift)
        return shift

    @staticmethod
    async def blind_closeout_shift(
        db: AsyncSession, shift_id: str, payload: CashRegisterShiftClose
    ) -> CashRegisterShift:
        """
        Executes blind closeout:
        1. Calculates expected cash balance: Opening Float + Cash Sales - Cash Expenses - Cash Refunds.
        2. Compares against cashier-entered counted cash.
        3. Sets variance & is_balanced flag.
        4. Locks if balanced; requires explanation/manager review if variance != 0.
        """
        stmt = select(CashRegisterShift).where(CashRegisterShift.id == shift_id)
        res = await db.execute(stmt)
        shift = res.scalar_one_or_none()
        if not shift:
            raise ValueError("Cash register shift not found.")
        if shift.status != "OPEN":
            raise ValueError(f"Shift is already {shift.status}.")

        now = CashboxService._utc_now()

        # 1. Cash In: Payments recorded via cash during this shift
        pay_stmt = select(func.coalesce(func.sum(Payment.amount), 0.0)).where(
            and_(
                Payment.branch_id == shift.branch_id,
                Payment.method == "cash",
                Payment.payment_date >= shift.opened_at,
                Payment.payment_date <= now,
            )
        )
        cash_in = float((await db.execute(pay_stmt)).scalar() or 0.0)

        # 2. Cash Out: Cash Expenses recorded during this shift
        exp_stmt = select(func.coalesce(func.sum(Expense.amount), 0.0)).where(
            and_(
                Expense.branch_id == shift.branch_id,
                Expense.shift_id == shift.id,
                Expense.payment_method == "cash",
            )
        )
        cash_exp = float((await db.execute(exp_stmt)).scalar() or 0.0)

        # 3. Cash Refunds
        ref_stmt = select(func.coalesce(func.sum(Refund.amount), 0.0)).where(
            and_(
                Refund.branch_id == shift.branch_id,
                Refund.shift_id == shift.id,
                Refund.refund_payment_method == "cash",
            )
        )
        cash_ref = float((await db.execute(ref_stmt)).scalar() or 0.0)

        expected = round(shift.opening_float + cash_in - cash_exp - cash_ref, 2)
        counted = round(payload.closing_counted_cash, 2)
        variance = round(counted - expected, 2)
        is_balanced = abs(variance) < 0.01

        if not is_balanced and not payload.variance_reason:
            raise ValueError(
                f"Shift has a variance of ₹{variance:.2f}. Mandatory explanation comment is required to close."
            )

        shift.closed_at = now
        shift.closing_denominations = payload.closing_denominations
        shift.closing_counted_cash = counted
        shift.expected_cash = expected
        shift.variance = variance
        shift.is_balanced = is_balanced
        shift.variance_reason = payload.variance_reason
        shift.manager_override_by_id = payload.manager_override_by_id
        shift.status = "CLOSED" if is_balanced else "LOCKED"
        if payload.notes:
            shift.notes = (shift.notes or "") + "\n" + payload.notes

        shift.audit_meta = {
            "cash_in_sales": cash_in,
            "cash_out_expenses": cash_exp,
            "cash_out_refunds": cash_ref,
            "closed_at": now.isoformat(),
        }

        await db.commit()
        await db.refresh(shift)
        return shift

    @staticmethod
    async def create_expense(
        db: AsyncSession, payload: ExpenseCreate, user_id: Optional[str]
    ) -> Expense:
        """
        Records an expense voucher.
        If is_spare_purchase is True, automatically increases inventory on-hand!
        Records balanced double-entry in the general ledger.
        """
        accounts = await CashboxService.get_or_create_default_accounts(db, payload.branch_id)
        now = CashboxService._utc_now()
        exp_number = f"EXP-{now.strftime('%Y%m')}-{secrets.token_hex(4).upper()}"

        expense = Expense(
            expense_number=exp_number,
            branch_id=payload.branch_id,
            shift_id=payload.shift_id,
            category=payload.category,
            amount=payload.amount,
            payment_method=payload.payment_method,
            payee_name=payload.payee_name,
            receipt_photo_url=payload.receipt_photo_url,
            narration=payload.narration,
            ticket_id=payload.ticket_id,
            is_spare_purchase=payload.is_spare_purchase,
            inventory_item_id=payload.inventory_item_id,
            quantity=payload.quantity,
            unit_cost=payload.unit_cost,
            created_by_id=user_id,
        )
        db.add(expense)
        await db.flush()

        # If spare part cash purchase, auto-record stock movement
        if payload.is_spare_purchase and payload.inventory_item_id and payload.quantity > 0:
            await InventoryService.record_stock_movement(
                session=db,
                branch_id=payload.branch_id,
                inventory_item_id=payload.inventory_item_id,
                movement_type="PURCHASE_DIRECT",
                quantity_change=payload.quantity,
                unit_cost=payload.unit_cost or (payload.amount / payload.quantity),
                reference_type="DIRECT_CASH_EXPENSE",
                reference_id=expense.id,
                notes=f"Cash Purchase {expense.expense_number}: {payload.narration or ''}",
            )

        # Double-entry posting:
        # Determine Expense Account
        if payload.category.lower().startswith("subcontract") or payload.ticket_id:
            exp_acc = accounts["5010_EXP_SUBCONTRACT"]
        elif payload.is_spare_purchase:
            exp_acc = accounts["5020_EXP_SPARE"]
        else:
            exp_acc = accounts["5090_EXP_GENERAL"]

        # Determine Payment Asset Account
        if payload.payment_method == "cash":
            pay_acc = accounts["1010_CASH"]
        elif payload.payment_method == "upi":
            pay_acc = accounts["1020_UPI"]
        else:
            pay_acc = accounts["1030_CARD"]

        await CashboxService.record_double_entry(
            db=db,
            branch_id=payload.branch_id,
            shift_id=payload.shift_id,
            reference_type="EXPENSE",
            reference_id=expense.id,
            entries=[
                {
                    "account_id": exp_acc.id,
                    "debit": payload.amount,
                    "credit": 0.0,
                    "narration": f"Expense {expense.expense_number}: {payload.category} - {payload.payee_name or ''}",
                },
                {
                    "account_id": pay_acc.id,
                    "debit": 0.0,
                    "credit": payload.amount,
                    "narration": f"Payment via {payload.payment_method} for {expense.expense_number}",
                },
            ],
        )

        await db.commit()
        await db.refresh(expense)
        return expense

    @staticmethod
    async def create_refund(
        db: AsyncSession, payload: RefundCreate, user_id: Optional[str]
    ) -> Refund:
        """
        Creates customer refund with double-entry reversal.
        """
        accounts = await CashboxService.get_or_create_default_accounts(db, payload.branch_id)
        now = CashboxService._utc_now()
        ref_number = f"REF-{now.strftime('%Y%m')}-{secrets.token_hex(4).upper()}"

        refund = Refund(
            refund_number=ref_number,
            branch_id=payload.branch_id,
            shift_id=payload.shift_id,
            sale_id=payload.sale_id,
            invoice_id=payload.invoice_id,
            credit_note_id=payload.credit_note_id,
            client_id=payload.client_id,
            original_payment_method=payload.original_payment_method,
            refund_payment_method=payload.refund_payment_method,
            amount=payload.amount,
            reason=payload.reason,
            status="completed",
            approved_by_id=user_id,
            notes=payload.notes,
        )
        db.add(refund)
        await db.flush()

        sales_acc = accounts["4010_SALES"]
        pay_acc = accounts["1010_CASH"] if payload.refund_payment_method == "cash" else accounts["1020_UPI"]

        await CashboxService.record_double_entry(
            db=db,
            branch_id=payload.branch_id,
            shift_id=payload.shift_id,
            reference_type="REFUND",
            reference_id=refund.id,
            entries=[
                {
                    "account_id": sales_acc.id,
                    "debit": payload.amount,
                    "credit": 0.0,
                    "narration": f"Sales reversal for refund {refund.refund_number}",
                },
                {
                    "account_id": pay_acc.id,
                    "debit": 0.0,
                    "credit": payload.amount,
                    "narration": f"Payout via {payload.refund_payment_method} for refund {refund.refund_number}",
                },
            ],
        )

        await db.commit()
        await db.refresh(refund)
        return refund

    @staticmethod
    async def calculate_ticket_profitability(
        db: AsyncSession, ticket_id: str
    ) -> ProfitPerTicketResponse:
        """
        Computes:
        Net Ticket Profit = Total Bill − Parts Cost − Subcontract Expenses − Tech Commission
        """
        t_stmt = select(Ticket).where(Ticket.id == ticket_id)
        t_res = await db.execute(t_stmt)
        ticket = t_res.scalar_one_or_none()
        if not ticket:
            raise ValueError("Ticket not found")

        # 1. Total Bill
        # Check if Sale exists for this ticket
        sale_stmt = select(Sale).where(Sale.ticket_id == ticket_id)
        sale_res = await db.execute(sale_stmt)
        sale = sale_res.scalar_one_or_none()

        total_bill = sale.grand_total if sale else (ticket.grand_total or 0.0)

        # 2. Parts Cost
        parts_stmt = select(TicketPart).where(TicketPart.ticket_id == ticket_id)
        parts = (await db.execute(parts_stmt)).scalars().all()
        parts_cost = sum((p.unit_cost or 0.0) * (p.quantity or 1.0) for p in parts)

        # 3. Subcontract Expenses
        exp_stmt = select(func.coalesce(func.sum(Expense.amount), 0.0)).where(Expense.ticket_id == ticket_id)
        subcontract_expenses = float((await db.execute(exp_stmt)).scalar() or 0.0)

        # 4. Tech Commission
        comm_stmt = select(func.coalesce(func.sum(TechnicianCommission.commission_amount), 0.0)).where(
            TechnicianCommission.ticket_id == ticket_id
        )
        tech_commission = float((await db.execute(comm_stmt)).scalar() or 0.0)

        # If no commission record yet, calculate provisional from labor
        if tech_commission == 0.0 and ticket.assigned_tech_id:
            labor_stmt = select(TicketLabor).where(TicketLabor.ticket_id == ticket_id)
            labors = (await db.execute(labor_stmt)).scalars().all()
            total_labor = sum(l.total_price or 0.0 for l in labors)
            tech_commission = round(total_labor * 0.15, 2)  # default 15% labor commission

        net_profit = round(total_bill - parts_cost - subcontract_expenses - tech_commission, 2)
        margin = round((net_profit / total_bill) * 100, 2) if total_bill > 0 else 0.0

        return ProfitPerTicketResponse(
            ticket_id=ticket.id,
            ticket_number=ticket.ticket_number,
            total_bill=round(total_bill, 2),
            parts_cost=round(parts_cost, 2),
            subcontract_expenses=round(subcontract_expenses, 2),
            tech_commission=round(tech_commission, 2),
            net_profit=net_profit,
            margin_percentage=margin,
        )

    @staticmethod
    async def compute_payroll_report(
        db: AsyncSession, month: int, year: int, branch_id: Optional[str] = None
    ) -> PayrollReportResponse:
        """
        Computes monthly commission payroll for all technicians.
        """
        # Fetch technician users
        from app.models.rbac import Role
        tech_stmt = select(User).join(Role, User.role_id == Role.id).where(Role.slug == "technician")
        if branch_id:
            tech_stmt = tech_stmt.where(User.branch_id == branch_id)
        techs = (await db.execute(tech_stmt)).scalars().all()
        if not techs:
            all_u = select(User)
            if branch_id:
                all_u = all_u.where(User.branch_id == branch_id)
            techs = (await db.execute(all_u.limit(5))).scalars().all()

        report_items: List[PayrollReportItem] = []
        total_payout = 0.0

        for tech in techs:
            # Completed tickets in period
            t_stmt = select(Ticket).where(
                and_(
                    Ticket.assigned_tech_id == tech.id,
                    Ticket.status == "Delivered",
                    func.strftime("%m", Ticket.created_at) == f"{month:02d}",
                    func.strftime("%Y", Ticket.created_at) == str(year),
                )
            )
            tickets = (await db.execute(t_stmt)).scalars().all()
            tickets_count = len(tickets)

            # Sum commission records
            c_stmt = select(func.coalesce(func.sum(TechnicianCommission.commission_amount), 0.0)).where(
                and_(
                    TechnicianCommission.technician_id == tech.id,
                    TechnicianCommission.period_month == month,
                    TechnicianCommission.period_year == year,
                )
            )
            comm_earned = float((await db.execute(c_stmt)).scalar() or 0.0)

            # Sum gross labor billed
            ticket_ids = [t.id for t in tickets]
            gross_labor = 0.0
            if ticket_ids:
                l_stmt = select(func.coalesce(func.sum(TicketLabor.total_price), 0.0)).where(
                    TicketLabor.ticket_id.in_(ticket_ids)
                )
                gross_labor = float((await db.execute(l_stmt)).scalar() or 0.0)

            if comm_earned == 0.0 and gross_labor > 0:
                comm_earned = round(gross_labor * 0.15, 2)

            report_items.append(
                PayrollReportItem(
                    technician_id=tech.id,
                    technician_name=tech.full_name,
                    tickets_completed=tickets_count,
                    gross_labor_billed=gross_labor,
                    total_commission_earned=comm_earned,
                    status="Pending Payroll Approval" if comm_earned > 0 else "N/A",
                )
            )
            total_payout += comm_earned

        return PayrollReportResponse(
            period_month=month,
            period_year=year,
            branch_id=branch_id,
            technicians=report_items,
            total_payroll_commission=round(total_payout, 2),
        )

    @staticmethod
    async def get_consolidated_financials(db: AsyncSession) -> ConsolidatedFinancialsResponse:
        """
        Consolidates P&L, Cashbox, UPI and Accounts Receivable across all branches.
        """
        branches = (await db.execute(select(Branch))).scalars().all()
        summaries: List[BranchFinancialSummary] = []

        total_cash = 0.0
        total_bank_upi = 0.0
        total_ar = 0.0
        total_rev = 0.0
        total_exp = 0.0

        for b in branches:
            accounts = await CashboxService.get_or_create_default_accounts(db, b.id)

            cash_bal = accounts["1010_CASH"].balance
            upi_bal = accounts["1020_UPI"].balance
            ar_bal = accounts["1040_AR"].balance
            rev_bal = accounts["4010_SALES"].balance

            # Total expenses: 5010 + 5020 + 5030 + 5090
            exp_bal = (
                accounts["5010_EXP_SUBCONTRACT"].balance
                + accounts["5020_EXP_SPARE"].balance
                + accounts["5030_EXP_COMMISSION"].balance
                + accounts["5090_EXP_GENERAL"].balance
            )

            net_p = round(rev_bal - exp_bal, 2)

            summaries.append(
                BranchFinancialSummary(
                    branch_id=b.id,
                    branch_name=b.name,
                    cash_balance=round(cash_bal, 2),
                    bank_upi_balance=round(upi_bal, 2),
                    receivables_balance=round(ar_bal, 2),
                    total_revenue=round(rev_bal, 2),
                    total_expenses=round(exp_bal, 2),
                    net_profit=net_p,
                )
            )

            total_cash += cash_bal
            total_bank_upi += upi_bal
            total_ar += ar_bal
            total_rev += rev_bal
            total_exp += exp_bal

        return ConsolidatedFinancialsResponse(
            consolidated_at=CashboxService._utc_now(),
            branches=summaries,
            total_cash=round(total_cash, 2),
            total_bank_upi=round(total_bank_upi, 2),
            total_receivables=round(total_ar, 2),
            total_revenue=round(total_rev, 2),
            total_expenses=round(total_exp, 2),
            net_consolidated_profit=round(total_rev - total_exp, 2),
        )

    @staticmethod
    async def handle_upi_webhook(
        db: AsyncSession, payload: UpiWebhookPayload
    ) -> UpiWebhookResponse:
        """
        Processes real-time UPI QR incoming webhook from payment gateway.
        Matches transaction against ticket, sale, or invoice, records payment,
        and posts double-entry.
        """
        m_id = payload.merchant_transaction_id.strip()

        # Try match ticket
        t_stmt = select(Ticket).where(or_(Ticket.id == m_id, Ticket.ticket_number == m_id))
        t_res = await db.execute(t_stmt)
        ticket = t_res.scalar_one_or_none()

        branch_id = ticket.branch_id if ticket else "branch-main"
        accounts = await CashboxService.get_or_create_default_accounts(db, branch_id)

        # Record payment
        pay_num = f"PAY-UPI-{secrets.token_hex(4).upper()}"
        payment = Payment(
            payment_number=pay_num,
            branch_id=branch_id,
            method="upi",
            amount=payload.amount,
            transaction_reference=payload.transaction_id,
            is_reconciled=True,
            reconciled_at=CashboxService._utc_now(),
            bank_statement_reference=f"UPI-VPA-{payload.payer_vpa or 'DIRECT'}",
            notes=f"Auto-settled via UPI Webhook event {payload.event}",
        )

        matched_entity = "unknown"
        if ticket:
            payment.sale_id = None
            matched_entity = f"ticket:{ticket.ticket_number}"
        else:
            # Check sale
            s_stmt = select(Sale).where(or_(Sale.id == m_id, Sale.sale_number == m_id))
            sale = (await db.execute(s_stmt)).scalar_one_or_none()
            if sale:
                payment.sale_id = sale.id
                payment.branch_id = sale.branch_id
                sale.paid_amount += payload.amount
                sale.balance_due = max(0.0, sale.grand_total - sale.paid_amount)
                matched_entity = f"sale:{sale.sale_number}"

        db.add(payment)
        await db.flush()

        # Double-entry posting: Debit 1020_UPI, Credit 4010_SALES
        upi_acc = accounts["1020_UPI"]
        sales_acc = accounts["4010_SALES"]
        await CashboxService.record_double_entry(
            db=db,
            branch_id=branch_id,
            shift_id=None,
            reference_type="PAYMENT",
            reference_id=payment.id,
            entries=[
                {
                    "account_id": upi_acc.id,
                    "debit": payload.amount,
                    "credit": 0.0,
                    "narration": f"UPI Instant Credit ref {payload.transaction_id}",
                },
                {
                    "account_id": sales_acc.id,
                    "debit": 0.0,
                    "credit": payload.amount,
                    "narration": f"Revenue settled via UPI for {matched_entity}",
                },
            ],
        )

        await db.commit()
        return UpiWebhookResponse(
            success=True,
            message="UPI Payment confirmed and posted to double-entry ledger",
            matched_entity=matched_entity,
            payment_id=payment.id,
        )
