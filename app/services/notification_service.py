import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import (
    NotificationTemplate,
    NotificationOptOut,
    NotificationLog,
    generate_short_code,
)
from app.models.base import utc_now


DEFAULT_TEMPLATES = [
    {
        "name": "ticket_intake",
        "channel": "whatsapp",
        "category": "service_transactional",
        "dlt_template_id": "110716182900001",
        "dlt_sender_id": "OMNISP",
        "subject": "Device Received for Service - {{ticket_number}}",
        "body": "Hello {{client_name}}, your device {{brand}} {{model}} has been received for service at {{branch_name}}. Ticket: {{ticket_number}}. Track live progress here: {{tracking_url}}",
        "variables": ["client_name", "brand", "model", "branch_name", "ticket_number", "tracking_url"],
    },
    {
        "name": "estimate_approval",
        "channel": "whatsapp",
        "category": "service_transactional",
        "dlt_template_id": "110716182900002",
        "dlt_sender_id": "OMNISP",
        "subject": "Cost Estimate Approval Required - {{ticket_number}}",
        "body": "Dear {{client_name}}, the diagnostic estimate for {{ticket_number}} is Rs. {{amount}}. Please review parts & labor and approve online in 1 click: {{tracking_url}}",
        "variables": ["client_name", "ticket_number", "amount", "tracking_url"],
    },
    {
        "name": "ready_for_pickup",
        "channel": "whatsapp",
        "category": "service_transactional",
        "dlt_template_id": "110716182900003",
        "dlt_sender_id": "OMNISP",
        "subject": "Device Ready for Pickup - {{ticket_number}}",
        "body": "Great news {{client_name}}! Your {{brand}} {{model}} ({{ticket_number}}) has passed QA inspection and is ready for pickup at {{branch_name}}. Net balance due: Rs. {{balance_due}}. View invoice & pay online: {{tracking_url}}",
        "variables": ["client_name", "brand", "model", "ticket_number", "branch_name", "balance_due", "tracking_url"],
    },
    {
        "name": "feedback_survey_24h",
        "channel": "whatsapp",
        "category": "reminder",
        "dlt_template_id": "110716182900004",
        "dlt_sender_id": "OMNISP",
        "subject": "How was your service experience? - {{ticket_number}}",
        "body": "Hi {{client_name}}, thank you for choosing {{branch_name}} for repairing {{ticket_number}}. How was your experience? Rate our technician & service in 30 seconds: {{tracking_url}}",
        "variables": ["client_name", "branch_name", "ticket_number", "tracking_url"],
    },
    {
        "name": "maintenance_reminder_6m",
        "channel": "whatsapp",
        "category": "reminder",
        "dlt_template_id": "110716182900005",
        "dlt_sender_id": "OMNISP",
        "subject": "6-Month Preventive Maintenance Due - {{brand}} {{model}}",
        "body": "Hello {{client_name}}, it has been 6 months since your {{brand}} {{model}} was serviced. Routine preventive maintenance prevents sudden breakdown. Book an inspection at {{branch_name}}: {{tracking_url}}",
        "variables": ["client_name", "brand", "model", "branch_name", "tracking_url"],
    },
    {
        "name": "warranty_expiry_15d",
        "channel": "whatsapp",
        "category": "reminder",
        "dlt_template_id": "110716182900006",
        "dlt_sender_id": "OMNISP",
        "subject": "Warranty Expiring in 15 Days - {{ticket_number}}",
        "body": "Notice: The repair warranty for your {{brand}} {{model}} (Ticket {{ticket_number}}) expires in 15 days. Need an extended warranty plan or complimentary health check? Contact {{branch_phone}}: {{tracking_url}}",
        "variables": ["client_name", "brand", "model", "ticket_number", "branch_phone", "tracking_url"],
    },
    {
        "name": "seasonal_campaign",
        "channel": "whatsapp",
        "category": "campaign",
        "dlt_template_id": "110716182900007",
        "dlt_sender_id": "OMNISP",
        "subject": "Seasonal Service Offer from {{branch_name}}",
        "body": "Special Seasonal Offer from {{branch_name}}! Get 20% off on preventive diagnostics and priority service. Claim your offer here: {{tracking_url}}",
        "variables": ["branch_name", "tracking_url"],
    },
]


class NotificationService:
    """
    Central notification engine managing template substitution, DLT/TRAI opt-out scrubbing,
    delivery audit logs, and short-link click tracking.
    """

    @staticmethod
    async def ensure_default_templates(db: AsyncSession, branch_id: Optional[str] = None):
        """Seed default system templates if not already present."""
        for tmpl_data in DEFAULT_TEMPLATES:
            stmt = select(NotificationTemplate).where(
                NotificationTemplate.name == tmpl_data["name"],
                NotificationTemplate.channel == tmpl_data["channel"],
            )
            res = await db.execute(stmt)
            existing = res.scalar_one_or_none()
            if not existing:
                tmpl = NotificationTemplate(
                    branch_id=branch_id,
                    name=tmpl_data["name"],
                    channel=tmpl_data["channel"],
                    category=tmpl_data["category"],
                    dlt_template_id=tmpl_data["dlt_template_id"],
                    dlt_sender_id=tmpl_data["dlt_sender_id"],
                    subject=tmpl_data["subject"],
                    body=tmpl_data["body"],
                    variables=tmpl_data["variables"],
                    is_active=True,
                )
                db.add(tmpl)
        await db.commit()

    @staticmethod
    async def is_opted_out(db: AsyncSession, phone: Optional[str], email: Optional[str] = None, channel: str = "whatsapp") -> bool:
        """
        Scrub against TRAI / DLT Opt-Out Registry.
        Returns True if the recipient has opted out of this channel or 'all'.
        """
        if not phone and not email:
            return False

        conditions = []
        if phone:
            clean_phone = phone.strip().replace(" ", "").replace("-", "")
            if clean_phone.startswith("+91"):
                clean_phone = clean_phone[3:]
            elif clean_phone.startswith("91") and len(clean_phone) > 10:
                clean_phone = clean_phone[2:]

            conditions.append(NotificationOptOut.phone.like(f"%{clean_phone}%"))

        if email:
            conditions.append(NotificationOptOut.email == email.strip().lower())

        if not conditions:
            return False

        stmt = select(NotificationOptOut).where(
            or_(*conditions),
            NotificationOptOut.opt_out == True,
            or_(NotificationOptOut.channel == "all", NotificationOptOut.channel == channel),
        ).limit(1)
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()
        return record is not None

    @staticmethod
    def render_content(template_body: str, variables: Dict[str, Any]) -> str:
        """Replace {{variable_name}} with values."""
        content = template_body
        for key, val in variables.items():
            pattern = re.compile(r"\{\{\s*" + re.escape(key) + r"\s*\}\}")
            content = pattern.sub(str(val) if val is not None else "", content)
        return content

    @classmethod
    async def dispatch(
        cls,
        db: AsyncSession,
        *,
        channel: str = "whatsapp",
        recipient_phone: Optional[str] = None,
        recipient_email: Optional[str] = None,
        template_name: Optional[str] = None,
        custom_content: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None,
        category: str = "transactional",
        ticket_id: Optional[str] = None,
        client_id: Optional[str] = None,
        branch_id: Optional[str] = None,
        target_tracking_url: Optional[str] = None,
        base_url: str = "http://localhost:3000",
    ) -> NotificationLog:
        """
        Dispatches a notification, applying TRAI opt-out scrubbing,
        click-token generation, template rendering, and delivery audit logging.
        """
        variables = variables or {}
        now = utc_now()

        # 1. Generate click token and short-url
        click_token = generate_short_code()
        short_click_url = f"{base_url}/public/c/{click_token}"

        # Put tracking_url in variables if target_tracking_url is given
        if target_tracking_url:
            variables.setdefault("tracking_url", short_click_url)
        elif "tracking_url" not in variables:
            variables["tracking_url"] = short_click_url

        # 2. Lookup template if provided
        dlt_id = None
        template_obj = None
        if template_name:
            stmt = select(NotificationTemplate).where(
                NotificationTemplate.name == template_name,
                NotificationTemplate.channel == channel,
                NotificationTemplate.is_active == True,
            )
            res = await db.execute(stmt)
            template_obj = res.scalar_one_or_none()
            if template_obj:
                dlt_id = template_obj.dlt_template_id
                body_to_render = template_obj.body
                category = template_obj.category
            else:
                body_to_render = custom_content or f"Notification for ticket {ticket_id or ''}"
        else:
            body_to_render = custom_content or "OmniSuite notification"

        # 3. Render message text
        rendered_text = cls.render_content(body_to_render, variables)

        # 4. Check DLT / TRAI Opt-Out Registry
        is_opted = await cls.is_opted_out(db, recipient_phone, recipient_email, channel)

        if is_opted and category in ["service_promotional", "campaign", "reminder"]:
            # Compliance requirement: Block promotional/reminder notifications for opted-out users
            log = NotificationLog(
                branch_id=branch_id,
                ticket_id=ticket_id,
                client_id=client_id,
                channel=channel,
                recipient_phone=recipient_phone,
                recipient_email=recipient_email,
                template_id=template_obj.id if template_obj else None,
                template_name=template_name,
                category=category,
                dlt_template_id=dlt_id,
                content=rendered_text,
                status="opted_out",
                error_reason="Blocked: Recipient registered in TRAI/DLT NDNC Opt-Out Registry",
                cost=0.0,
                click_token=click_token,
                click_target_url=target_tracking_url,
                sent_at=now,
            )
            db.add(log)
            await db.commit()
            await db.refresh(log)
            return log

        # 5. Dispatch / Delivery simulation (production connects to WhatsApp Cloud API, Gupshup, or Twilio)
        cost = 0.12 if channel == "sms" else (0.45 if channel == "whatsapp" else 0.02)
        vendor_msg_id = f"MSG-{now.strftime('%Y%m%d')}-{click_token}"

        log = NotificationLog(
            branch_id=branch_id,
            ticket_id=ticket_id,
            client_id=client_id,
            channel=channel,
            recipient_phone=recipient_phone,
            recipient_email=recipient_email,
            template_id=template_obj.id if template_obj else None,
            template_name=template_name,
            category=category,
            dlt_template_id=dlt_id,
            content=rendered_text,
            status="delivered",
            vendor_message_id=vendor_msg_id,
            cost=cost,
            click_token=click_token,
            click_target_url=target_tracking_url,
            sent_at=now,
            delivered_at=now,
        )
        db.add(log)
        await db.commit()
        await db.refresh(log)
        return log

    @staticmethod
    async def track_click(
        db: AsyncSession,
        short_code: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Optional[str]:
        """
        Records short-link click metrics and returns the target URL for redirection.
        """
        stmt = select(NotificationLog).where(NotificationLog.click_token == short_code)
        res = await db.execute(stmt)
        log = res.scalar_one_or_none()
        if not log:
            return None

        log.click_count += 1
        log.clicked_at = utc_now()
        if user_agent:
            log.user_agent = user_agent[:250]
        if ip_address:
            log.ip_address = ip_address[:50]

        await db.commit()
        return log.click_target_url
