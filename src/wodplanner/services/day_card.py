"""DayCard model and builder — enriched Appointment shape for calendar rendering."""

from datetime import datetime, timedelta
from typing import Mapping
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from wodplanner.models.calendar import Appointment
from wodplanner.models.friends import Friend
from wodplanner.services.one_rep_max import has_1rm_exercise as _check_1rm

_TZ = ZoneInfo("Europe/Amsterdam")


def _is_signup_open(appt_name: str, appt_start: datetime, now: datetime) -> bool:
    """Check if sign-up window has opened for an appointment.

    CF101/101 classes open 14 weeks before; regular classes open 7 days before.
    """
    start_tz = appt_start.replace(tzinfo=_TZ) if appt_start.tzinfo is None else appt_start
    now_tz = now.replace(tzinfo=_TZ) if now.tzinfo is None else now
    if "CF101" in appt_name or "101" in appt_name:
        signup_opens = start_tz - timedelta(weeks=14)
    else:
        signup_opens = start_tz - timedelta(days=7)
    return now_tz >= signup_opens


def _has_1rm(appt_name: str, schedule_by_class_type: Mapping[str, object]) -> bool:
    """Check if appointment's matched Schedule contains a 1RM exercise."""
    sched = schedule_by_class_type.get(appt_name)
    if sched is None:
        return False
    return (
        _check_1rm(getattr(sched, "warmup_mobility", None))
        or _check_1rm(getattr(sched, "strength_specialty", None))
        or _check_1rm(getattr(sched, "metcon", None))
    )


class DayCard(BaseModel):
    """Enriched Appointment for calendar rendering."""

    id: int
    name: str
    time_start: str
    time_end: str
    spots_taken: int
    spots_total: int
    status: str
    date_start: str
    date_end: str
    friends: list[Friend] = []
    has_1rm: bool = False
    signup_open: bool = False
    is_past: bool = False


def build_day_cards(
    appointments: list[Appointment],
    friends_by_appt_id: Mapping[int, list[Friend] | None],
    schedule_by_class_type: Mapping[str, object],
    now: datetime,
) -> list[DayCard]:
    """Build DayCard objects from raw appointment data."""
    cards: list[DayCard] = []
    now_tz = now.replace(tzinfo=_TZ) if now.tzinfo is None else now
    for appt in appointments:
        target_date = appt.date_start.date()
        actual_start = datetime.combine(target_date, appt.date_start.time(), tzinfo=appt.date_start.tzinfo)
        actual_start_tz = actual_start.replace(tzinfo=_TZ) if actual_start.tzinfo is None else actual_start

        cards.append(
            DayCard(
                id=appt.id_appointment,
                name=appt.name,
                time_start=appt.date_start.strftime("%H:%M"),
                time_end=appt.date_end.strftime("%H:%M"),
                spots_taken=appt.total_subscriptions,
                spots_total=appt.max_subscriptions,
                status=appt.status,
                date_start=target_date.isoformat(),
                date_end=target_date.isoformat(),
                friends=friends_by_appt_id.get(appt.id_appointment) or [],
                has_1rm=_has_1rm(appt.name, schedule_by_class_type),
                signup_open=_is_signup_open(appt.name, actual_start, now),
                is_past=actual_start_tz < now_tz,
            )
        )
    return cards
