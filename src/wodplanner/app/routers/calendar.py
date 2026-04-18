"""Calendar and schedule endpoints."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from wodplanner.api.client import WodAppClient
from wodplanner.app.dependencies import get_client_from_session, get_friends_service
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
    client: WodAppClient = Depends(get_client_from_session),
    friends_service: FriendsService = Depends(get_friends_service),
) -> DayScheduleResponse:
    """Get the schedule for a specific day (defaults to today)."""
    target_date = day or date.today()
    appointments = client.get_day_schedule(target_date)

    # Get friend IDs for lookup
    friend_ids = friends_service.get_appuser_ids() if include_friends else set()
    friends_map = {f.appuser_id: f for f in friends_service.get_all()} if include_friends else {}

    result_appointments = []
    for appt in appointments:
        friends_in_class = []

        # If include_friends is enabled, fetch member list (cached)
        if include_friends and friend_ids:
            try:
                members, _ = client.get_appointment_members(
                    appt.id_appointment,
                    appt.date_start,
                    appt.date_end,
                )
                for member in members:
                    if member.id_appuser in friend_ids:
                        friend = friends_map.get(member.id_appuser)
                        friends_in_class.append(
                            FriendInClass(
                                id=member.id_appuser,
                                name=friend.name if friend else member.name,
                            )
                        )
            except Exception:
                pass

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
    client: WodAppClient = Depends(get_client_from_session),
    friends_service: FriendsService = Depends(get_friends_service),
) -> list[DayScheduleResponse]:
    """Get the schedule for a week starting from the given date."""
    from datetime import timedelta

    start = start_date or date.today()

    # Get friend IDs for lookup (once, not per day)
    friend_ids = friends_service.get_appuser_ids() if include_friends else set()
    friends_map = {f.appuser_id: f for f in friends_service.get_all()} if include_friends else {}

    result = []

    for i in range(7):
        target_date = start + timedelta(days=i)
        appointments = client.get_day_schedule(target_date)

        result_appointments = []
        for appt in appointments:
            friends_in_class = []

            if include_friends and friend_ids:
                try:
                    members, _ = client.get_appointment_members(
                        appt.id_appointment,
                        appt.date_start,
                        appt.date_end,
                    )
                    for member in members:
                        if member.id_appuser in friend_ids:
                            friend = friends_map.get(member.id_appuser)
                            friends_in_class.append(
                                FriendInClass(
                                    id=member.id_appuser,
                                    name=friend.name if friend else member.name,
                                )
                            )
                except Exception:
                    pass

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
