"""Calendar and schedule endpoints."""

from datetime import date
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

    result_appointments = []
    for appt in appointments:
        friends_list = friends_by_appt.get(appt.id_appointment) or []
        friends_in_class = [FriendInClass(id=f.appuser_id, name=f.name) for f in friends_list]

        result_appointments.append(
            AppointmentResponse(
                id=appt.id_appointment,
                name=appt.name,
                date_start=appt.date_start.date().isoformat(),
                date_end=appt.date_end.date().isoformat(),
                time_start=appt.date_start.strftime("%H:%M"),
                time_end=appt.date_end.strftime("%H:%M"),
                spots_taken=appt.total_subscriptions,
                spots_total=appt.max_subscriptions,
                status=appt.status,
                friends=friends_in_class,
            )
        )

    return DayScheduleResponse(
        date=target_date.isoformat(),
        appointments=result_appointments,
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
    from datetime import timedelta

    start = start_date or date.today()

    friends = friends_service.get_all(session.user_id) if include_friends else []

    result = []

    for i in range(7):
        target_date = start + timedelta(days=i)
        appointments = client.get_day_schedule(target_date)

        friends_by_appt = find_friends_in_appointments(appointments, friends, client) if include_friends else {}

        result_appointments = []
        for appt in appointments:
            friends_list = friends_by_appt.get(appt.id_appointment) or []
            friends_in_class = [FriendInClass(id=f.appuser_id, name=f.name) for f in friends_list]

            result_appointments.append(
                AppointmentResponse(
                    id=appt.id_appointment,
                    name=appt.name,
                    date_start=appt.date_start.date().isoformat(),
                    date_end=appt.date_end.date().isoformat(),
                    time_start=appt.date_start.strftime("%H:%M"),
                    time_end=appt.date_end.strftime("%H:%M"),
                    spots_taken=appt.total_subscriptions,
                    spots_total=appt.max_subscriptions,
                    status=appt.status,
                    friends=friends_in_class,
                )
            )

        result.append(
            DayScheduleResponse(
                date=target_date.isoformat(),
                appointments=result_appointments,
            )
        )

    return result
