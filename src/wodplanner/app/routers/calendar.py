"""Calendar and schedule endpoints."""

from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from wodplanner.api.client import WodAppClient
from wodplanner.app.dependencies import (
    get_client_from_session,
    get_friends_service,
    require_session,
)
from wodplanner.models.auth import AuthSession
from wodplanner.services.day_card import DayCard, build_day_cards
from wodplanner.services.friend_presence import find_friends_in_appointments
from wodplanner.services.friends import FriendsService

router = APIRouter(prefix="/calendar", tags=["calendar"])


class FriendInClass(BaseModel):
    """A friend signed up for a class."""

    id: int
    name: str


class AppointmentResponse(BaseModel):
    """Appointment summary for schedule view."""

    id: int
    name: str
    date_start: str
    date_end: str
    time_start: str
    time_end: str
    spots_taken: int
    spots_total: int
    status: str  # "open", "closed", "subscribed"
    friends: list[FriendInClass] = []  # Friends signed up for this class


class DayScheduleResponse(BaseModel):
    """Schedule for a single day."""

    date: str
    appointments: list[AppointmentResponse]


def _project_card(card: DayCard) -> AppointmentResponse:
    """Project a DayCard to the JSON wire shape, converting Friend → FriendInClass."""
    return AppointmentResponse(
        id=card.id,
        name=card.name,
        date_start=card.date_start,
        date_end=card.date_end,
        time_start=card.time_start,
        time_end=card.time_end,
        spots_taken=card.spots_taken,
        spots_total=card.spots_total,
        status=card.status,
        friends=[FriendInClass(id=f.appuser_id, name=f.name) for f in card.friends],
    )


@router.get("/day", response_model=DayScheduleResponse)
def get_day_schedule(
    day: date | None = Query(default=None, description="Date in YYYY-MM-DD format"),
    include_friends: bool = Query(
        default=False, description="Include friends info (slower, fetches details)"
    ),
    session: Annotated[AuthSession, Depends(require_session)] = None,  # type: ignore[assignment]
    client: WodAppClient = Depends(get_client_from_session),
    friends_service: FriendsService = Depends(get_friends_service),
) -> DayScheduleResponse:
    """Get the schedule for a specific day (defaults to today)."""
    target_date = day or date.today()
    appointments = client.get_day_schedule(target_date)

    friends = friends_service.get_all(session.user_id) if include_friends else []
    friends_by_appt = find_friends_in_appointments(appointments, friends, client) if include_friends else {}

    cards = build_day_cards(appointments, friends_by_appt, {}, datetime.now(), calendar_date=target_date)
    return DayScheduleResponse(
        date=target_date.isoformat(),
        appointments=[_project_card(c) for c in cards],
    )


@router.get("/week", response_model=list[DayScheduleResponse])
def get_week_schedule(
    start_date: date | None = Query(
        default=None, description="Start date (defaults to today)"
    ),
    include_friends: bool = Query(
        default=False, description="Include friends info (slower, fetches details)"
    ),
    session: Annotated[AuthSession, Depends(require_session)] = None,  # type: ignore[assignment]
    client: WodAppClient = Depends(get_client_from_session),
    friends_service: FriendsService = Depends(get_friends_service),
) -> list[DayScheduleResponse]:
    """Get the schedule for a week starting from the given date."""
    start = start_date or date.today()
    friends = friends_service.get_all(session.user_id) if include_friends else []
    now = datetime.now()

    result = []
    for i in range(7):
        target_date = start + timedelta(days=i)
        appointments = client.get_day_schedule(target_date)
        friends_by_appt = find_friends_in_appointments(appointments, friends, client) if include_friends else {}
        cards = build_day_cards(appointments, friends_by_appt, {}, now, calendar_date=target_date)
        result.append(
            DayScheduleResponse(
                date=target_date.isoformat(),
                appointments=[_project_card(c) for c in cards],
            )
        )

    return result
