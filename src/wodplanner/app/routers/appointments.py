"""Appointment detail and subscription endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from wodplanner.api.client import WodAppClient, WodAppError
from wodplanner.app.dependencies import get_client_from_session
from wodplanner.utils.dates import parse_api_datetime

router = APIRouter(prefix="/appointments", tags=["appointments"])


class MemberResponse(BaseModel):
    """A member signed up for an appointment."""

    id: int
    name: str


class AppointmentDetailResponse(BaseModel):
    """Detailed appointment information."""

    id: int
    name: str
    date_start: str
    date_end: str
    time_start: str
    time_end: str
    spots_taken: int
    spots_total: int
    waiting_list_enabled: bool
    waiting_list_count: int
    subscription_opens_at: str
    is_open_for_signup: bool
    has_spots_available: bool
    is_subscribed: bool
    members: list[MemberResponse]
    waiting_list_members: list[MemberResponse]


class SubscribeRequest(BaseModel):
    """Request to subscribe to an appointment."""

    date_start: str  # Format: "YYYY-MM-DD HH:MM"
    date_end: str  # Format: "YYYY-MM-DD HH:MM"


class SubscribeResponse(BaseModel):
    """Response from subscribe action."""

    success: bool
    message: str


@router.get("/{appointment_id}", response_model=AppointmentDetailResponse)
def get_appointment_details(
    appointment_id: int,
    date_start: str,  # Query param: "YYYY-MM-DD HH:MM"
    date_end: str,  # Query param: "YYYY-MM-DD HH:MM"
    client: WodAppClient = Depends(get_client_from_session),
) -> AppointmentDetailResponse:
    """Get detailed information about an appointment including participants."""
    try:
        start = parse_api_datetime(date_start)
        end = parse_api_datetime(date_end)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use 'YYYY-MM-DD HH:MM'",
        )

    try:
        details = client.get_appointment_details(appointment_id, start, end)
    except WodAppError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return AppointmentDetailResponse(
        id=details.id_appointment,
        name=details.name,
        date_start=details.date_start.date().isoformat(),
        date_end=details.date_end.date().isoformat(),
        time_start=details.date_start.strftime("%H:%M"),
        time_end=details.date_end.strftime("%H:%M"),
        spots_taken=details.subscriptions.total,
        spots_total=details.max_subscriptions,
        waiting_list_enabled=bool(details.waiting_list),
        waiting_list_count=details.waitinglist.total,
        subscription_opens_at=details.subscription_open_date,
        is_open_for_signup=details.is_open_for_signup(),
        has_spots_available=details.has_spots_available(),
        is_subscribed=details.is_user_subscribed(),
        members=[
            MemberResponse(id=m.id_appuser, name=m.name)
            for m in details.subscriptions.members
        ],
        waiting_list_members=[
            MemberResponse(id=m.id_appuser, name=m.name)
            for m in details.waitinglist.members
        ],
    )


@router.post("/{appointment_id}/subscribe", response_model=SubscribeResponse)
def subscribe_to_appointment(
    appointment_id: int,
    request: SubscribeRequest,
    client: WodAppClient = Depends(get_client_from_session),
) -> SubscribeResponse:
    """Subscribe to an appointment."""
    try:
        start = parse_api_datetime(request.date_start)
        end = parse_api_datetime(request.date_end)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use 'YYYY-MM-DD HH:MM'",
        )

    try:
        result = client.subscribe(appointment_id, start, end)
        return SubscribeResponse(
            success=result.subscribedWithSuccess == 1,
            message=result.notice,
        )
    except WodAppError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{appointment_id}/waitinglist", response_model=SubscribeResponse)
def subscribe_to_waitinglist(
    appointment_id: int,
    request: SubscribeRequest,
    client: WodAppClient = Depends(get_client_from_session),
) -> SubscribeResponse:
    """Subscribe to an appointment's waiting list."""
    try:
        start = parse_api_datetime(request.date_start)
        end = parse_api_datetime(request.date_end)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use 'YYYY-MM-DD HH:MM'",
        )

    try:
        result = client.subscribe_waitinglist(appointment_id, start, end)
        return SubscribeResponse(
            success=True,
            message=result.notice,
        )
    except WodAppError as e:
        raise HTTPException(status_code=400, detail=str(e))
