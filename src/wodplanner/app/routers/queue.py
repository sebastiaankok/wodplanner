"""Queue endpoints for auto-signup feature."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from wodplanner.api.client import WodAppClient
from wodplanner.app.dependencies import get_client_from_session, get_scheduler, require_session
from wodplanner.models.auth import AuthSession
from wodplanner.models.queue import QueuedSignup, QueueStatus
from wodplanner.services.scheduler import SignupScheduler

router = APIRouter(prefix="/queue", tags=["queue"])


class QueueItemResponse(BaseModel):
    """Response model for a queued signup."""

    id: int
    appointment_id: int
    appointment_name: str
    date: str
    time_start: str
    time_end: str
    signup_opens_at: str
    status: str
    result_message: str | None
    created_at: str | None


class AddToQueueRequest(BaseModel):
    """Request to add an appointment to the auto-signup queue."""

    appointment_id: int
    date_start: str  # Format: "YYYY-MM-DD HH:MM"
    date_end: str  # Format: "YYYY-MM-DD HH:MM"


class AddToQueueResponse(BaseModel):
    """Response after adding to queue."""

    success: bool
    message: str
    queue_item: QueueItemResponse | None


def _signup_to_response(signup: QueuedSignup) -> QueueItemResponse:
    """Convert a QueuedSignup to response model."""
    return QueueItemResponse(
        id=signup.id,
        appointment_id=signup.appointment_id,
        appointment_name=signup.appointment_name,
        date=signup.date_start.date().isoformat(),
        time_start=signup.date_start.strftime("%H:%M"),
        time_end=signup.date_end.strftime("%H:%M"),
        signup_opens_at=signup.signup_opens_at.isoformat(),
        status=signup.status,
        result_message=signup.result_message,
        created_at=signup.created_at.isoformat() if signup.created_at else None,
    )


@router.get("", response_model=list[QueueItemResponse])
def list_queue(
    include_completed: bool = False,
    scheduler: SignupScheduler = Depends(get_scheduler),
) -> list[QueueItemResponse]:
    """List all items in the auto-signup queue."""
    signups = scheduler.queue_service.get_all(include_completed=include_completed)
    return [_signup_to_response(s) for s in signups]


@router.post("", response_model=AddToQueueResponse)
def add_to_queue(
    request: AddToQueueRequest,
    session: Annotated[AuthSession, Depends(require_session)],
    client: WodAppClient = Depends(get_client_from_session),
    scheduler: SignupScheduler = Depends(get_scheduler),
) -> AddToQueueResponse:
    """Add an appointment to the auto-signup queue."""
    try:
        date_start = datetime.strptime(request.date_start, "%Y-%m-%d %H:%M")
        date_end = datetime.strptime(request.date_end, "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use 'YYYY-MM-DD HH:MM'",
        )

    # Get appointment details to validate and get signup open time
    try:
        details = client.get_appointment_details(
            request.appointment_id,
            date_start,
            date_end,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get appointment: {e}")

    # Check if already subscribed
    if details.is_user_subscribed():
        return AddToQueueResponse(
            success=False,
            message="You are already subscribed to this class",
            queue_item=None,
        )

    # Parse the signup open date (format: "DD-MM-YYYY HH:MM")
    try:
        signup_opens_at = datetime.strptime(
            details.subscription_open_date, "%d-%m-%Y %H:%M"
        )
    except ValueError:
        raise HTTPException(
            status_code=500,
            detail=f"Could not parse signup open date: {details.subscription_open_date}",
        )

    # Check if signup is already open and has spots
    if details.is_open_for_signup() and details.has_spots_available():
        return AddToQueueResponse(
            success=False,
            message="Signup is already open with spots available. Use the subscribe endpoint instead.",
            queue_item=None,
        )

    # Create the queued signup with user credentials
    signup = QueuedSignup(
        appointment_id=request.appointment_id,
        appointment_name=details.name,
        date_start=date_start,
        date_end=date_end,
        signup_opens_at=signup_opens_at,
        status=QueueStatus.PENDING,
        user_token=session.token,
        user_id=session.user_id,
    )

    # Add to queue and schedule
    signup = scheduler.add_signup(signup)

    return AddToQueueResponse(
        success=True,
        message=f"Added to queue. Will auto-signup at {signup_opens_at.strftime('%Y-%m-%d %H:%M')}",
        queue_item=_signup_to_response(signup),
    )


@router.get("/{queue_id}", response_model=QueueItemResponse)
def get_queue_item(
    queue_id: int,
    scheduler: SignupScheduler = Depends(get_scheduler),
) -> QueueItemResponse:
    """Get a specific queue item."""
    signup = scheduler.queue_service.get(queue_id)
    if not signup:
        raise HTTPException(status_code=404, detail="Queue item not found")
    return _signup_to_response(signup)


@router.delete("/{queue_id}")
def cancel_queue_item(
    queue_id: int,
    scheduler: SignupScheduler = Depends(get_scheduler),
) -> dict:
    """Cancel a queued signup."""
    signup = scheduler.queue_service.get(queue_id)
    if not signup:
        raise HTTPException(status_code=404, detail="Queue item not found")

    if signup.status not in (QueueStatus.PENDING, QueueStatus.SCHEDULED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel signup with status: {signup.status}",
        )

    scheduler.cancel_signup(queue_id)
    return {"success": True, "message": "Signup cancelled"}


@router.get("/jobs/scheduled")
def get_scheduled_jobs(
    scheduler: SignupScheduler = Depends(get_scheduler),
) -> list[dict]:
    """Get all scheduled jobs (for debugging)."""
    return scheduler.get_scheduled_jobs()
