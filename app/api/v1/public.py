from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.tracking_service import TrackingService
from app.services.notification_service import NotificationService
from app.schemas.tracking import (
    PublicTrackingResponse,
    EstimateApprovalRequest,
    EstimateApprovalResponse,
    EstimateRejectionRequest,
    EstimateRejectionResponse,
    UPIInitiateRequest,
    UPIInitiateResponse,
    FeedbackSubmitRequest,
    FeedbackSubmitResponse,
)
from app.schemas.notification import (
    PublicOptOutRequest,
    PublicOptOutResponse,
)

router = APIRouter(tags=["Public Work Order Tracking"])


def get_client_ip(request: Request) -> str:
    """Extract client IP, taking into account X-Forwarded-For if behind a proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


# ============================================================
# 1. GET /public/track/{token} - Rate-Limited Public Work Order
# ============================================================
@router.get("/track/{token}", response_model=PublicTrackingResponse)
async def get_public_tracking(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Public tracking endpoint (zero authentication required).
    Returns only safe fields, strictly strips internal technician costs & notes,
    and provides mobile-friendly 5-stage milestone tracking.
    """
    client_ip = get_client_ip(request)
    data = await TrackingService.get_public_data(db, token, client_ip)
    return data


# ============================================================
# 2. Estimate Approval & Rejection via Token
# ============================================================
@router.post("/track/{token}/estimate/approve", response_model=EstimateApprovalResponse)
async def approve_estimate_via_track_token(
    token: str,
    payload: Optional[EstimateApprovalRequest] = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Customer 1-click approves diagnostic estimate via tracking token."""
    client_ip = get_client_ip(request) if request else None
    notes = payload.customer_notes if payload else None
    return await TrackingService.approve_estimate(db, token, client_ip, notes)


@router.post("/estimate/{approval_token}/approve", response_model=EstimateApprovalResponse)
async def approve_estimate_via_approval_token(
    approval_token: str,
    payload: Optional[EstimateApprovalRequest] = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Customer 1-click approves diagnostic estimate via specific approval token."""
    client_ip = get_client_ip(request) if request else None
    notes = payload.customer_notes if payload else None
    return await TrackingService.approve_estimate(db, approval_token, client_ip, notes)


@router.post("/track/{token}/estimate/reject", response_model=EstimateRejectionResponse)
async def reject_estimate_via_track_token(
    token: str,
    payload: EstimateRejectionRequest,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Customer rejects diagnostic estimate with reason via tracking token."""
    client_ip = get_client_ip(request) if request else None
    return await TrackingService.reject_estimate(db, token, payload.rejection_reason, client_ip)


@router.post("/estimate/{approval_token}/reject", response_model=EstimateRejectionResponse)
async def reject_estimate_via_approval_token(
    approval_token: str,
    payload: EstimateRejectionRequest,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Customer rejects diagnostic estimate with reason via approval token."""
    client_ip = get_client_ip(request) if request else None
    return await TrackingService.reject_estimate(db, approval_token, payload.rejection_reason, client_ip)


# ============================================================
# 3. Online UPI Payment Initiation
# ============================================================
@router.post("/track/{token}/pay/upi", response_model=UPIInitiateResponse)
async def initiate_upi_payment(
    token: str,
    payload: Optional[UPIInitiateRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Generates standard NPCI UPI Intent Link and deep links for Google Pay,
    PhonePe, Paytm, and BHIM with QR code payload.
    """
    amount = payload.amount if payload else None
    notes = payload.notes if payload else None
    return await TrackingService.initiate_upi(db, token, amount, notes)


# ============================================================
# 4. Customer Feedback Survey Submission
# ============================================================
@router.post("/track/{token}/feedback", response_model=FeedbackSubmitResponse)
async def submit_ticket_feedback(
    token: str,
    payload: FeedbackSubmitRequest,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Submits 1-5 star ratings, NPS score, and feedback comments."""
    client_ip = get_client_ip(request) if request else None
    return await TrackingService.submit_feedback(db, token, payload.model_dump(), client_ip)


# ============================================================
# 5. Short Link Click Tracking Redirect: GET /public/c/{code}
# ============================================================
@router.get("/c/{short_code}")
async def track_notification_click(
    short_code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Tracks customer click on notification link (timestamp, IP, user-agent)
    and redirects to destination tracking or portal URL.
    """
    user_agent = request.headers.get("user-agent")
    client_ip = get_client_ip(request)
    target_url = await NotificationService.track_click(db, short_code, user_agent, client_ip)
    if not target_url:
        return {"status": "ok", "message": "Link verified", "target_url": "/"}
    return RedirectResponse(url=target_url, status_code=status.HTTP_302_FOUND)


# ============================================================
# 6. DLT / TRAI Opt-Out Unsubscribe
# ============================================================
@router.post("/opt-out", response_model=PublicOptOutResponse)
async def public_opt_out(
    payload: PublicOptOutRequest,
    db: AsyncSession = Depends(get_db),
):
    """Public customer opt-out endpoint for TRAI / DLT NDNC compliance."""
    from app.models.notification import NotificationOptOut
    from app.models.base import utc_now

    opt = NotificationOptOut(
        phone=payload.phone.strip(),
        channel=payload.channel,
        opt_out=True,
        reason=payload.reason,
        source="unsubscribe_link",
        opted_out_at=utc_now(),
    )
    db.add(opt)
    await db.commit()

    return {
        "success": True,
        "message": f"Successfully unsubscribed {payload.phone} from {payload.channel} promotional notifications.",
        "phone": payload.phone,
        "channel": payload.channel,
    }
