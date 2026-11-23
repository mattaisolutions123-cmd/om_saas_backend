import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from fastapi import HTTPException, status
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
import urllib.parse
import time

from app.models.ticket import Ticket, TicketPart, TicketLabor, TicketMedia, TicketEstimate
from app.models.client import Client
from app.models.asset import Asset
from app.models.branch import Branch
from app.models.feedback import CustomerFeedback
from app.models.payment_transaction import PaymentTransaction
from app.models.base import utc_now, to_utc


# In-memory rate limiting tracker: IP -> [(timestamp, count)]
_IP_RATE_LIMIT_CACHE: Dict[str, List[float]] = {}
RATE_LIMIT_MAX_REQUESTS = 60  # max 60 requests
RATE_LIMIT_WINDOW_SECONDS = 60  # per 60 seconds


def check_rate_limit(client_ip: str):
    """Enforces 60 requests / minute rate-limit on public tracking endpoints."""
    now = time.time()
    timestamps = _IP_RATE_LIMIT_CACHE.get(client_ip, [])
    # Filter out timestamps older than window
    valid_timestamps = [ts for ts in timestamps if now - ts < RATE_LIMIT_WINDOW_SECONDS]
    if len(valid_timestamps) >= RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please wait a moment before refreshing tracking details.",
            headers={"Retry-After": str(RATE_LIMIT_WINDOW_SECONDS)},
        )
    valid_timestamps.append(now)
    _IP_RATE_LIMIT_CACHE[client_ip] = valid_timestamps


def mask_phone(phone: Optional[str]) -> str:
    if not phone:
        return "N/A"
    clean = phone.strip()
    if len(clean) >= 10:
        return clean[:4] + "***" + clean[-3:]
    return clean[:2] + "***"


def mask_name(full_name: Optional[str]) -> str:
    if not full_name:
        return "Valued Customer"
    parts = full_name.strip().split()
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][0]}."


def mask_serial(serial: Optional[str]) -> Optional[str]:
    if not serial:
        return None
    s = serial.strip()
    if len(s) > 4:
        return s[:2] + "****" + s[-2:]
    return "****"


class TrackingService:
    """
    Public tracking and customer-interaction service.
    Guarantees strict data isolation, zero leak of internal technician costs,
    and mobile-optimized 5-stage progress computation.
    """

    @classmethod
    async def get_ticket_by_token(cls, db: AsyncSession, token: str) -> Ticket:
        stmt = (
            select(Ticket)
            .options(
                selectinload(Ticket.client),
                selectinload(Ticket.asset),
                selectinload(Ticket.branch),
                selectinload(Ticket.parts),
                selectinload(Ticket.labor_items),
                selectinload(Ticket.media),
                selectinload(Ticket.estimates),
            )
            .where(Ticket.tracking_token == token)
        )
        res = await db.execute(stmt)
        ticket = res.scalar_one_or_none()
        if not ticket:
            raise HTTPException(status_code=404, detail="Work order tracking token not found or expired.")
        return ticket

    @classmethod
    def compute_stages(cls, current_status: str, created_at: datetime, promised_date: Optional[datetime], handover_at: Optional[datetime]) -> Tuple[str, int, int, List[Dict[str, Any]]]:
        """
        Maps granular ticket pipeline status into 5 clear public milestones:
        0: Received (intake, counter, pending_inspection)
        1: Diagnosis (diagnosis, diagnosed, waiting_approval, estimate_pending)
        2: Repaired (in_progress, repair_in_progress, lathe_work, spare_wait, qa_pending)
        3: Ready (work_done, ready_for_pickup, ready)
        4: Delivered (delivered, handover_done, closed)
        """
        status_lower = current_status.lower()

        stage_mapping = {
            "intake": (0, "Received", "Device checked in at service counter"),
            "counter": (0, "Received", "Intake inspection completed"),
            "pending_inspection": (0, "Received", "Queued for diagnostic inspection"),

            "diagnosis": (1, "Diagnosis", "Diagnostic checks & disassembly underway"),
            "diagnosed": (1, "Diagnosis", "Root cause identified & estimate prepared"),
            "waiting_approval": (1, "Diagnosis", "Awaiting customer approval on estimate"),
            "estimate_pending": (1, "Diagnosis", "Detailed estimate under review"),

            "in_progress": (2, "Repaired", "Component repair & replacement in progress"),
            "repair_in_progress": (2, "Repaired", "Precision machining and assembly underway"),
            "lathe_work": (2, "Repaired", "Precision lathe turning in progress"),
            "spare_wait": (2, "Repaired", "Awaiting OEM spare part delivery"),
            "qa_pending": (2, "Repaired", "Repairs completed, undergoing quality test"),

            "work_done": (3, "Ready", "QA Passed. Cleaned & packaged for pickup"),
            "ready_for_pickup": (3, "Ready", "Ready for handover at service counter"),
            "ready": (3, "Ready", "Ready for handover & final settlement"),

            "delivered": (4, "Delivered", "Device collected and warranty initiated"),
            "handover_done": (4, "Delivered", "Handover completed with digital acknowledgment"),
            "closed": (4, "Delivered", "Ticket closed & archived"),
        }

        stage_idx, stage_name, description = stage_mapping.get(
            status_lower, (2, "Repaired", f"Service status: {current_status}")
        )

        stage_defs = [
            {"key": "received", "label": "Received", "desc": "Device logged into service laboratory"},
            {"key": "diagnosis", "label": "Diagnosis", "desc": "Diagnostic teardown & estimate approval"},
            {"key": "repaired", "label": "Repaired", "desc": "Parts replaced & mechanical assembly"},
            {"key": "ready", "label": "Ready", "desc": "Quality checks passed & ready for pickup"},
            {"key": "delivered", "label": "Delivered", "desc": "Handed over to customer with warranty"},
        ]

        stages_list = []
        for i, s_def in enumerate(stage_defs):
            if i < stage_idx:
                s_status = "completed"
                s_time = created_at + timedelta(hours=i * 6)
            elif i == stage_idx:
                s_status = "current"
                s_time = utc_now()
            else:
                s_status = "upcoming"
                s_time = promised_date if i == 3 else None

            stages_list.append({
                "key": s_def["key"],
                "label": s_def["label"],
                "status": s_status,
                "timestamp": s_time,
                "description": s_def["desc"] if i != stage_idx else description,
            })

        progress_pct = int((stage_idx + 1) * 20)
        return stage_name, stage_idx, progress_pct, stages_list

    @classmethod
    async def get_public_data(cls, db: AsyncSession, token: str, client_ip: str) -> Dict[str, Any]:
        """
        Rate-limited public query returning strictly safe customer-facing data.
        """
        check_rate_limit(client_ip)
        ticket = await cls.get_ticket_by_token(db, token)

        current_stage, stage_idx, progress_pct, stages_list = cls.compute_stages(
            ticket.status, ticket.created_at, ticket.promised_delivery_date, ticket.handover_at
        )

        # Safe client
        client_data = {
            "name": mask_name(ticket.client.name if ticket.client else None),
            "phone_masked": mask_phone(ticket.client.phone if ticket.client else None),
            "email_masked": None,
        }

        # Safe asset
        asset_data = None
        if ticket.asset:
            asset_data = {
                "brand": ticket.asset.brand or "OEM",
                "model_name": ticket.asset.model or ticket.asset.name or "Industrial Equipment",
                "category": ticket.asset.asset_type or "Equipment",
                "serial_number_masked": mask_serial(ticket.asset.identifier),
            }

        # Safe branch
        branch_name = ticket.branch.name if ticket.branch else "OmniSuite Tech Hub"
        branch_phone = "+91 98200 11223"
        branch_addr = "Industrial Area, Andheri East, Mumbai, Maharashtra 400093"
        upi_vpa = "omnisuite@icici"
        branch_data = {
            "name": branch_name,
            "phone": branch_phone,
            "address": branch_addr,
            "upi_vpa": upi_vpa,
            "merchant_name": branch_name,
        }

        # Safe billing breakdown (billed values to customer only)
        billing_data = {
            "total_parts_cost": round(float(ticket.total_parts_cost), 2),
            "total_labor_cost": round(float(ticket.total_labor_cost), 2),
            "tax_total": round(float(ticket.tax_total), 2),
            "discount_amount": round(float(ticket.discount_amount), 2),
            "grand_total": round(float(ticket.grand_total), 2),
            "advance_deposit": round(float(ticket.advance_deposit), 2),
            "paid_amount": round(float(ticket.paid_amount), 2),
            "balance_due": round(float(ticket.balance_due), 2),
            "currency": "INR",
        }

        # Estimate details if present
        estimate_data = None
        if ticket.estimates:
            # Get latest estimate
            latest_est = sorted(ticket.estimates, key=lambda e: e.created_at or datetime.min, reverse=True)[0]
            is_expired = False
            if latest_est.expires_at and to_utc(latest_est.expires_at) < utc_now():
                is_expired = True

            # Safe line items (customer selling prices only)
            safe_items = []
            if latest_est.line_items:
                for itm in latest_est.line_items:
                    safe_items.append({
                        "description": itm.get("description") or itm.get("name", "Service item"),
                        "type": itm.get("type", "part"),
                        "quantity": float(itm.get("quantity", 1)),
                        "unit_price": float(itm.get("unit_price", 0)),
                        "tax_rate": float(itm.get("tax_rate", 18.0)),
                        "total_price": float(itm.get("total_price", 0)),
                    })

            estimate_data = {
                "id": latest_est.id,
                "estimate_number": latest_est.estimate_number,
                "approval_token": latest_est.approval_token,
                "approval_status": latest_est.approval_status,
                "parts_subtotal": round(float(latest_est.parts_subtotal), 2),
                "labor_subtotal": round(float(latest_est.labor_subtotal), 2),
                "tax_total": round(float(latest_est.tax_total), 2),
                "grand_total": round(float(latest_est.grand_total), 2),
                "line_items": safe_items,
                "customer_notes": latest_est.customer_notes,
                "expires_at": latest_est.expires_at,
                "approved_at": latest_est.approved_at,
                "is_expired": is_expired,
            }

        # Inspection photos
        photos_list = []
        for media in ticket.media:
            photos_list.append({
                "id": media.id,
                "media_type": media.media_type,  # before, diagnostic_proof, after
                "file_url": media.file_url,
                "file_name": media.file_name or "Inspection Photo",
                "notes": media.notes,
                "created_at": media.created_at,
            })

        # Check existing customer feedback
        f_stmt = select(CustomerFeedback).where(CustomerFeedback.ticket_id == ticket.id)
        f_res = await db.execute(f_stmt)
        feedback_obj = f_res.scalar_one_or_none()
        feedback_data = None
        has_feedback = False
        if feedback_obj:
            has_feedback = True
            feedback_data = {
                "overall_rating": feedback_obj.overall_rating,
                "technician_rating": feedback_obj.technician_rating,
                "nps_score": feedback_obj.nps_score,
                "turnaround_satisfaction": feedback_obj.turnaround_satisfaction,
                "pricing_satisfaction": feedback_obj.pricing_satisfaction,
                "comments": feedback_obj.comments,
                "submitted_at": feedback_obj.submitted_at,
            }

        return {
            "ticket_id": ticket.id,
            "ticket_number": ticket.ticket_number,
            "ticket_type": ticket.ticket_type,
            "tracking_token": ticket.tracking_token,
            "created_at": ticket.created_at,
            "promised_delivery_date": ticket.promised_delivery_date,
            "status": ticket.status,
            "status_display": ticket.status.replace("_", " ").title(),
            "current_stage": current_stage,
            "stage_index": stage_idx,
            "progress_percentage": progress_pct,
            "stages": stages_list,
            "problem_reported": ticket.problem_reported,
            "diagnosis_notes": ticket.diagnosis_notes,
            "qa_status": ticket.qa_status,
            "client": client_data,
            "asset": asset_data,
            "branch": branch_data,
            "billing": billing_data,
            "estimate": estimate_data,
            "photos": photos_list,
            "has_submitted_feedback": has_feedback,
            "feedback": feedback_data,
        }

    @classmethod
    async def approve_estimate(
        cls,
        db: AsyncSession,
        token: str,
        customer_ip: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Approves estimate by approval_token OR ticket tracking_token.
        Unpauses the ticket if threshold pause was active, updates ticket status to in_progress.
        """
        # Look up by approval_token first, then by ticket tracking_token
        stmt = select(TicketEstimate).where(TicketEstimate.approval_token == token)
        res = await db.execute(stmt)
        estimate = res.scalar_one_or_none()

        if not estimate:
            # Try tracking_token
            t_stmt = select(Ticket).options(selectinload(Ticket.estimates)).where(Ticket.tracking_token == token)
            t_res = await db.execute(t_stmt)
            ticket = t_res.scalar_one_or_none()
            if ticket and ticket.estimates:
                estimate = sorted(ticket.estimates, key=lambda e: e.created_at or datetime.min, reverse=True)[0]

        if not estimate:
            raise HTTPException(status_code=404, detail="Estimate not found for the provided token.")

        if estimate.approval_status == "approved":
            return {
                "success": True,
                "estimate_number": estimate.estimate_number,
                "approval_status": "approved",
                "approved_at": estimate.approved_at or utc_now(),
                "message": "Estimate has already been approved previously.",
            }

        now = utc_now()
        estimate.approval_status = "approved"
        estimate.approved_at = now
        estimate.customer_ip = customer_ip
        if notes:
            estimate.customer_notes = notes

        # Unpause and update associated ticket
        t_stmt = select(Ticket).where(Ticket.id == estimate.ticket_id)
        t_res = await db.execute(t_stmt)
        ticket = t_res.scalar_one_or_none()
        if ticket:
            if ticket.is_paused:
                ticket.is_paused = False
                ticket.pause_reason = None
            if ticket.status in ["diagnosed", "waiting_approval", "estimate_pending"]:
                ticket.status = "in_progress"

        await db.commit()
        return {
            "success": True,
            "estimate_number": estimate.estimate_number,
            "approval_status": "approved",
            "approved_at": now,
            "message": "Estimate approved successfully. Repair work will commence immediately.",
        }

    @classmethod
    async def reject_estimate(
        cls,
        db: AsyncSession,
        token: str,
        rejection_reason: str,
        customer_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Rejects estimate with customer provided reason.
        """
        stmt = select(TicketEstimate).where(TicketEstimate.approval_token == token)
        res = await db.execute(stmt)
        estimate = res.scalar_one_or_none()

        if not estimate:
            t_stmt = select(Ticket).options(selectinload(Ticket.estimates)).where(Ticket.tracking_token == token)
            t_res = await db.execute(t_stmt)
            ticket = t_res.scalar_one_or_none()
            if ticket and ticket.estimates:
                estimate = sorted(ticket.estimates, key=lambda e: e.created_at or datetime.min, reverse=True)[0]

        if not estimate:
            raise HTTPException(status_code=404, detail="Estimate not found for the provided token.")

        estimate.approval_status = "rejected"
        estimate.rejection_reason = rejection_reason
        estimate.customer_ip = customer_ip

        # Pause ticket with customer rejected reason
        t_stmt = select(Ticket).where(Ticket.id == estimate.ticket_id)
        t_res = await db.execute(t_stmt)
        ticket = t_res.scalar_one_or_none()
        if ticket:
            ticket.is_paused = True
            ticket.pause_reason = f"Customer declined estimate: {rejection_reason[:100]}"

        await db.commit()
        return {
            "success": True,
            "estimate_number": estimate.estimate_number,
            "approval_status": "rejected",
            "rejection_reason": rejection_reason,
            "message": "Estimate rejected. A service coordinator will contact you shortly.",
        }

    @classmethod
    async def initiate_upi(
        cls,
        db: AsyncSession,
        token: str,
        amount: Optional[float] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generates standard UPI Intent Link and deep links for Google Pay, PhonePe, Paytm, and BHIM.
        """
        ticket = await cls.get_ticket_by_token(db, token)

        pay_amount = amount if amount is not None and amount > 0 else ticket.balance_due
        if pay_amount <= 0:
            pay_amount = ticket.grand_total if ticket.grand_total > 0 else 500.0

        pay_amount = round(pay_amount, 2)
        txn_ref = f"TXN-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"
        upi_vpa = "omnisuite@icici"
        merchant_name = ticket.branch.name if ticket.branch else "OmniSuite Technologies"

        # Standard NPCI UPI Intent URL spec
        # upi://pay?pa=<vpa>&pn=<name>&am=<amount>&tn=<note>&tr=<ref>&cu=INR
        encoded_pn = urllib.parse.quote(merchant_name)
        note = f"Bill for {ticket.ticket_number}"
        encoded_tn = urllib.parse.quote(note)

        upi_intent_url = f"upi://pay?pa={upi_vpa}&pn={encoded_pn}&am={pay_amount:.2f}&tn={encoded_tn}&tr={txn_ref}&cu=INR"

        # Vendor specific deep links
        gpay_link = f"tez://upi/pay?pa={upi_vpa}&pn={encoded_pn}&am={pay_amount:.2f}&tn={encoded_tn}&tr={txn_ref}&cu=INR"
        phonepe_link = f"phonepe://pay?pa={upi_vpa}&pn={encoded_pn}&am={pay_amount:.2f}&tn={encoded_tn}&tr={txn_ref}&cu=INR"
        paytm_link = f"paytmmp://pay?pa={upi_vpa}&pn={encoded_pn}&am={pay_amount:.2f}&tn={encoded_tn}&tr={txn_ref}&cu=INR"
        bhim_link = upi_intent_url

        # Record payment transaction
        txn = PaymentTransaction(
            ticket_id=ticket.id,
            branch_id=ticket.branch_id,
            client_id=ticket.client_id,
            amount=pay_amount,
            payment_method="upi",
            upi_vpa=upi_vpa,
            upi_intent_url=upi_intent_url,
            transaction_ref=txn_ref,
            status="initiated",
            metadata_json={
                "ticket_number": ticket.ticket_number,
                "notes": notes,
                "client_phone": ticket.client.phone if ticket.client else None,
            },
        )
        db.add(txn)
        await db.commit()

        return {
            "transaction_ref": txn_ref,
            "amount": pay_amount,
            "currency": "INR",
            "upi_vpa": upi_vpa,
            "merchant_name": merchant_name,
            "upi_intent_url": upi_intent_url,
            "qr_code_payload": upi_intent_url,
            "ticket_number": ticket.ticket_number,
            "payment_links": {
                "upi": upi_intent_url,
                "gpay": gpay_link,
                "phonepe": phonepe_link,
                "paytm": paytm_link,
                "bhim": bhim_link,
            },
            "status": "initiated",
        }

    @classmethod
    async def submit_feedback(
        cls,
        db: AsyncSession,
        token: str,
        feedback_data: Dict[str, Any],
        customer_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Records customer feedback & satisfaction rating for delivered ticket.
        """
        ticket = await cls.get_ticket_by_token(db, token)

        # Check existing feedback
        stmt = select(CustomerFeedback).where(CustomerFeedback.ticket_id == ticket.id)
        res = await db.execute(stmt)
        existing = res.scalar_one_or_none()

        now = utc_now()
        if existing:
            existing.overall_rating = feedback_data["overall_rating"]
            existing.technician_rating = feedback_data.get("technician_rating", 5)
            existing.nps_score = feedback_data.get("nps_score", 10)
            existing.turnaround_satisfaction = feedback_data.get("turnaround_satisfaction", "on_time")
            existing.pricing_satisfaction = feedback_data.get("pricing_satisfaction", "fair")
            existing.comments = feedback_data.get("comments")
            existing.recommend_to_others = feedback_data.get("recommend_to_others", True)
            existing.customer_ip = customer_ip
            existing.submitted_at = now
            await db.commit()
            return {
                "success": True,
                "message": "Feedback updated successfully. Thank you!",
                "submitted_at": now,
                "overall_rating": existing.overall_rating,
            }

        fb = CustomerFeedback(
            ticket_id=ticket.id,
            client_id=ticket.client_id,
            branch_id=ticket.branch_id,
            overall_rating=feedback_data["overall_rating"],
            technician_rating=feedback_data.get("technician_rating", 5),
            nps_score=feedback_data.get("nps_score", 10),
            turnaround_satisfaction=feedback_data.get("turnaround_satisfaction", "on_time"),
            pricing_satisfaction=feedback_data.get("pricing_satisfaction", "fair"),
            comments=feedback_data.get("comments"),
            recommend_to_others=feedback_data.get("recommend_to_others", True),
            customer_ip=customer_ip,
            submitted_at=now,
        )
        db.add(fb)
        await db.commit()

        return {
            "success": True,
            "message": "Feedback submitted successfully. Thank you for rating our service!",
            "submitted_at": now,
            "overall_rating": fb.overall_rating,
        }
