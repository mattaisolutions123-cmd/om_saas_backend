import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from fastapi import HTTPException
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation import AutomationRule, ScheduledJob, MarketingCampaign
from app.models.ticket import Ticket
from app.models.client import Client
from app.models.asset import Asset
from app.models.branch import Branch
from app.models.sales import Sale
from app.models.base import utc_now, to_utc
from app.services.notification_service import NotificationService


DEFAULT_RULES = [
    {
        "name": "Customer Feedback Survey 24h After Delivery",
        "code": "FEEDBACK_24H",
        "trigger_event": "ticket_delivered",
        "delay_hours": 24,
        "delay_days": 0,
        "advance_days": 0,
        "channel": "whatsapp",
        "template_name": "feedback_survey_24h",
        "conditions": {},
    },
    {
        "name": "Preventive Maintenance Reminder After 6 Months",
        "code": "MAINTENANCE_6M",
        "trigger_event": "ticket_delivered",
        "delay_hours": 0,
        "delay_days": 180,
        "advance_days": 0,
        "channel": "whatsapp",
        "template_name": "maintenance_reminder_6m",
        "conditions": {},
    },
    {
        "name": "Warranty Expiry Notice 15 Days Prior",
        "code": "WARRANTY_15D",
        "trigger_event": "warranty_expiring_soon",
        "delay_hours": 0,
        "delay_days": 0,
        "advance_days": 15,
        "channel": "whatsapp",
        "template_name": "warranty_expiry_15d",
        "conditions": {},
    },
    {
        "name": "Seasonal Festive & Maintenance Blast to Segments",
        "code": "SEASONAL_PROMO",
        "trigger_event": "seasonal_schedule",
        "delay_hours": 0,
        "delay_days": 0,
        "advance_days": 0,
        "channel": "whatsapp",
        "template_name": "seasonal_campaign",
        "conditions": {},
    },
]


class AutomationService:
    """
    Automated customer engagement and recurring notification scheduler:
    1. Feedback survey 24h after delivery
    2. Maintenance reminder after 6 months (180 days)
    3. Warranty-expiry notice 15 days prior
    4. Seasonal campaigns to segments with DLT opt-out scrubbing
    """

    @staticmethod
    async def ensure_default_rules(db: AsyncSession, branch_id: Optional[str] = None):
        """Seeds built-in automation rules if missing."""
        for r_data in DEFAULT_RULES:
            stmt = select(AutomationRule).where(AutomationRule.code == r_data["code"])
            res = await db.execute(stmt)
            rule = res.scalar_one_or_none()
            if not rule:
                new_rule = AutomationRule(
                    branch_id=branch_id,
                    name=r_data["name"],
                    code=r_data["code"],
                    trigger_event=r_data["trigger_event"],
                    delay_hours=r_data["delay_hours"],
                    delay_days=r_data["delay_days"],
                    advance_days=r_data["advance_days"],
                    channel=r_data["channel"],
                    template_name=r_data["template_name"],
                    conditions=r_data["conditions"],
                    is_active=True,
                )
                db.add(new_rule)
        await db.commit()

    @classmethod
    async def schedule_ticket_delivery_automations(cls, db: AsyncSession, ticket: Ticket):
        """
        Triggered when a work order transitions to delivered/handover:
        1. Feedback survey scheduled 24 hours later
        2. Maintenance reminder scheduled 6 months (180 days) later
        """
        now = utc_now()

        # 1. 24h Feedback Survey
        r_feedback_stmt = select(AutomationRule).where(AutomationRule.code == "FEEDBACK_24H", AutomationRule.is_active == True)
        r_res = await db.execute(r_feedback_stmt)
        feedback_rule = r_res.scalar_one_or_none()

        delay_h = feedback_rule.delay_hours if feedback_rule else 24
        feedback_scheduled = now + timedelta(hours=delay_h)

        job_feedback = ScheduledJob(
            rule_id=feedback_rule.id if feedback_rule else None,
            ticket_id=ticket.id,
            client_id=ticket.client_id,
            asset_id=ticket.asset_id,
            job_type="feedback_survey_24h",
            scheduled_for=feedback_scheduled,
            status="scheduled",
        )
        db.add(job_feedback)

        # 2. 6-Month Maintenance Reminder (180 days)
        r_maint_stmt = select(AutomationRule).where(AutomationRule.code == "MAINTENANCE_6M", AutomationRule.is_active == True)
        m_res = await db.execute(r_maint_stmt)
        maint_rule = m_res.scalar_one_or_none()

        delay_d = maint_rule.delay_days if maint_rule else 180
        maint_scheduled = now + timedelta(days=delay_d)

        job_maint = ScheduledJob(
            rule_id=maint_rule.id if maint_rule else None,
            ticket_id=ticket.id,
            client_id=ticket.client_id,
            asset_id=ticket.asset_id,
            job_type="maintenance_reminder_6m",
            scheduled_for=maint_scheduled,
            status="scheduled",
        )
        db.add(job_maint)

        # 3. Schedule 15-day prior warranty-expiry notice (assuming 90 days repair warranty if unspecified)
        r_warr_stmt = select(AutomationRule).where(AutomationRule.code == "WARRANTY_15D", AutomationRule.is_active == True)
        w_res = await db.execute(r_warr_stmt)
        warr_rule = w_res.scalar_one_or_none()

        # Repair warranty ends 90 days after delivery by default; notice 15 days prior = 75 days
        advance_d = warr_rule.advance_days if warr_rule else 15
        warranty_duration_days = 90
        warr_notice_scheduled = now + timedelta(days=(warranty_duration_days - advance_d))

        job_warr = ScheduledJob(
            rule_id=warr_rule.id if warr_rule else None,
            ticket_id=ticket.id,
            client_id=ticket.client_id,
            asset_id=ticket.asset_id,
            job_type="warranty_expiry_15d",
            scheduled_for=warr_notice_scheduled,
            status="scheduled",
        )
        db.add(job_warr)

        await db.commit()

    @classmethod
    async def run_automation_sweep(cls, db: AsyncSession, base_url: str = "http://localhost:3000") -> Dict[str, Any]:
        """
        Executes all due scheduled jobs (where scheduled_for <= utc_now() and status == 'scheduled').
        Enforces TRAI DLT scrubbing before sending.
        """
        now = utc_now()
        stmt = (
            select(ScheduledJob)
            .options(
                selectinload(ScheduledJob.ticket).selectinload(Ticket.asset),
                selectinload(ScheduledJob.ticket).selectinload(Ticket.branch),
                selectinload(ScheduledJob.client),
                selectinload(ScheduledJob.rule),
            )
            .where(
                ScheduledJob.status == "scheduled",
                ScheduledJob.scheduled_for <= now,
            )
        )
        res = await db.execute(stmt)
        due_jobs = res.scalars().all()

        processed_count = 0
        executed_count = 0
        opted_out_count = 0
        failed_count = 0
        summaries = []

        for job in due_jobs:
            processed_count += 1
            client = job.client
            ticket = job.ticket
            branch = ticket.branch if ticket else None
            asset = ticket.asset if ticket else None

            client_phone = client.phone if client else None
            client_email = client.email if client else None
            client_name = client.name if client else "Customer"

            branch_name = branch.name if branch else "OmniSuite Tech Lab"
            branch_phone = "+91 98200 11223"
            ticket_number = ticket.ticket_number if ticket else "N/A"
            brand = asset.brand if asset and asset.brand else "Industrial Unit"
            model = asset.model if asset and asset.model else (asset.name if asset else "Equipment")

            tracking_url = f"{base_url}/track/{ticket.tracking_token}" if ticket else f"{base_url}"

            variables = {
                "client_name": client_name,
                "ticket_number": ticket_number,
                "brand": brand,
                "model": model,
                "branch_name": branch_name,
                "branch_phone": branch_phone,
                "tracking_url": tracking_url,
                "balance_due": ticket.balance_due if ticket else 0.0,
            }

            channel = job.rule.channel if job.rule else "whatsapp"
            template_name = job.rule.template_name if job.rule else job.job_type

            try:
                log = await NotificationService.dispatch(
                    db,
                    channel=channel,
                    recipient_phone=client_phone,
                    recipient_email=client_email,
                    template_name=template_name,
                    variables=variables,
                    category="reminder",
                    ticket_id=job.ticket_id,
                    client_id=job.client_id,
                    branch_id=ticket.branch_id if ticket else None,
                    target_tracking_url=tracking_url,
                    base_url=base_url,
                )

                if log.status == "opted_out":
                    job.status = "skipped_opt_out"
                    job.executed_at = now
                    job.execution_result = {"status": "skipped", "reason": log.error_reason, "log_id": log.id}
                    opted_out_count += 1
                else:
                    job.status = "completed"
                    job.executed_at = now
                    job.execution_result = {"status": "delivered", "vendor_message_id": log.vendor_message_id, "log_id": log.id}
                    executed_count += 1

                if job.rule:
                    job.rule.execution_count += 1
                    job.rule.last_run_at = now

                summaries.append({
                    "job_id": job.id,
                    "job_type": job.job_type,
                    "recipient": client_phone,
                    "status": job.status,
                })

            except Exception as e:
                job.status = "failed"
                job.executed_at = now
                job.execution_result = {"status": "failed", "error": str(e)}
                failed_count += 1

        await db.commit()

        return {
            "processed_count": processed_count,
            "executed_count": executed_count,
            "opted_out_count": opted_out_count,
            "failed_count": failed_count,
            "jobs_summary": summaries,
        }

    @classmethod
    async def evaluate_segment(
        cls,
        db: AsyncSession,
        segment_type: str = "all",
        segment_criteria: Optional[Dict[str, Any]] = None,
        branch_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Dynamically filters customer database by audience criteria:
        - all: all clients
        - high_value: total spend >= min_spend (default ₹10,000)
        - inactive_90d: last ticket completed > 90 days ago
        - warranty_expired: clients whose warranty has expired
        - brand_specific: clients with matching equipment brand
        - pin_code_cluster: clients matching postal pin code
        Also performs TRAI opt-out scrubbing to surface eligible vs opted-out counts.
        """
        segment_criteria = segment_criteria or {}
        stmt = select(Client)
        if branch_id:
            stmt = stmt.where(Client.branch_id == branch_id)

        res = await db.execute(stmt)
        all_clients = res.scalars().all()

        matching_clients = []
        now = utc_now()

        for c in all_clients:
            matches = True

            # Calculate total spend from sales & tickets
            s_stmt = select(func.coalesce(func.sum(Sale.grand_total), 0.0)).where(Sale.client_id == c.id)
            s_res = await db.execute(s_stmt)
            total_sales_spent = float(s_res.scalar() or 0.0)

            t_stmt = select(func.coalesce(func.sum(Ticket.grand_total), 0.0)).where(Ticket.client_id == c.id)
            t_res = await db.execute(t_stmt)
            total_ticket_spent = float(t_res.scalar() or 0.0)

            total_spent = total_sales_spent + total_ticket_spent

            # Last ticket date
            lt_stmt = select(Ticket.created_at).where(Ticket.client_id == c.id).order_by(Ticket.created_at.desc()).limit(1)
            lt_res = await db.execute(lt_stmt)
            last_ticket_date = lt_res.scalar_one_or_none()

            if segment_type == "high_value":
                min_spend = float(segment_criteria.get("min_spend", 10000.0))
                if total_spent < min_spend:
                    matches = False

            elif segment_type == "inactive_90d":
                days = int(segment_criteria.get("days_inactive", 90))
                cutoff = now - timedelta(days=days)
                if last_ticket_date and to_utc(last_ticket_date) > cutoff:
                    matches = False

            elif segment_type == "brand_specific":
                target_brand = segment_criteria.get("brand", "").strip().lower()
                if target_brand:
                    # Check if client owns asset of this brand
                    a_stmt = select(Asset).where(Asset.client_id == c.id, func.lower(Asset.brand).like(f"%{target_brand}%"))
                    a_res = await db.execute(a_stmt)
                    has_brand = a_res.scalar_one_or_none()
                    if not has_brand:
                        matches = False

            elif segment_type == "pin_code_cluster":
                target_pin = segment_criteria.get("pin_code", "").strip()
                client_pin = c.postal_code or (c.address_details or {}).get("pincode") or ""
                if target_pin and target_pin not in client_pin:
                    matches = False

            if matches:
                # Check opt-out
                is_opted = await NotificationService.is_opted_out(db, c.phone, c.email, channel="whatsapp")
                matching_clients.append({
                    "id": c.id,
                    "name": c.name,
                    "phone": c.phone,
                    "email": c.email,
                    "total_spent": round(total_spent, 2),
                    "last_ticket_date": last_ticket_date,
                    "is_opted_out": is_opted,
                })

        total_matches = len(matching_clients)
        opted_out_count = sum(1 for c in matching_clients if c["is_opted_out"])
        eligible_count = total_matches - opted_out_count

        return {
            "segment_type": segment_type,
            "total_matches": total_matches,
            "eligible_count": eligible_count,
            "opted_out_count": opted_out_count,
            "sample_clients": matching_clients[:10],
        }

    @classmethod
    async def broadcast_campaign(
        cls,
        db: AsyncSession,
        campaign_id: str,
        base_url: str = "http://localhost:3000",
    ) -> Dict[str, Any]:
        """
        Broadcasts a marketing campaign to its designated audience segment,
        strictly respecting TRAI DLT NDNC opt-out scrub rules.
        """
        stmt = select(MarketingCampaign).where(MarketingCampaign.id == campaign_id)
        res = await db.execute(stmt)
        campaign = res.scalar_one_or_none()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found.")

        # Evaluate segment
        seg_result = await cls.evaluate_segment(
            db,
            segment_type=campaign.segment_type,
            segment_criteria=campaign.segment_criteria,
            branch_id=campaign.branch_id,
        )

        campaign.status = "in_progress"
        await db.commit()

        sent_count = 0
        delivered_count = 0
        failed_count = 0
        opt_out_count = 0

        # Fetch branch details
        branch_name = "OmniSuite Enterprise"
        if campaign.branch_id:
            b_stmt = select(Branch).where(Branch.id == campaign.branch_id)
            b_res = await db.execute(b_stmt)
            b_obj = b_res.scalar_one_or_none()
            if b_obj:
                branch_name = b_obj.name

        for client_info in seg_result["sample_clients"]:
            if client_info["is_opted_out"]:
                opt_out_count += 1
                continue

            try:
                variables = {
                    "client_name": client_info["name"],
                    "branch_name": branch_name,
                    "tracking_url": f"{base_url}/trends",
                }

                log = await NotificationService.dispatch(
                    db,
                    channel=campaign.channel,
                    recipient_phone=client_info["phone"],
                    recipient_email=client_info["email"],
                    template_name="seasonal_campaign" if not campaign.custom_message else None,
                    custom_content=campaign.custom_message,
                    variables=variables,
                    category="campaign",
                    client_id=client_info["id"],
                    branch_id=campaign.branch_id,
                    target_tracking_url=f"{base_url}/trends",
                    base_url=base_url,
                )

                sent_count += 1
                if log.status == "delivered":
                    delivered_count += 1
                elif log.status == "opted_out":
                    opt_out_count += 1
                else:
                    failed_count += 1

            except Exception:
                failed_count += 1

        campaign.sent_count = sent_count
        campaign.delivered_count = delivered_count
        campaign.failed_count = failed_count
        campaign.opt_out_count = opt_out_count
        campaign.status = "completed"
        await db.commit()

        return {
            "campaign_id": campaign.id,
            "name": campaign.name,
            "status": "completed",
            "sent_count": sent_count,
            "delivered_count": delivered_count,
            "failed_count": failed_count,
            "opt_out_count": opt_out_count,
        }
