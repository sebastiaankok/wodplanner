"""Shared calendar view builder — used by calendar_page and calendar_day_partial."""

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from wodplanner.api.client import WodAppClient
from wodplanner.models.auth import AuthSession
from wodplanner.services.friend_presence import find_friends_in_appointments
from wodplanner.services.friends import FriendsService
from wodplanner.services.one_rep_max import has_1rm_exercise
from wodplanner.services.schedule import ScheduleService
from wodplanner.services.schedule_lookup import match_schedules_for_date

logger = logging.getLogger(__name__)

_TZ = ZoneInfo("Europe/Amsterdam")


def is_signup_open(appt_name: str, appt_start: datetime) -> bool:
    now = datetime.now(_TZ)
    appt_start_tz = appt_start.replace(tzinfo=_TZ) if appt_start.tzinfo is None else appt_start
    if "CF101" in appt_name or "101" in appt_name:
        signup_opens = appt_start_tz - timedelta(weeks=14)
    else:
        signup_opens = appt_start_tz - timedelta(days=7)
    return now >= signup_opens


def build_calendar_view(
    session: AuthSession,
    target_date: date,
    client: WodAppClient,
    friends_service: FriendsService,
    schedule_service: ScheduleService,
    hidden_types: set[str],
) -> list[dict]:
    """Fetch and build appointment data list for calendar rendering."""
    appointments = client.get_day_schedule(target_date)
    visible = [a for a in appointments if a.name not in hidden_types]

    friends = friends_service.get_all(session.user_id)

    schedule_map = match_schedules_for_date(
        target_date, gym_id=session.gym_id, schedule_service=schedule_service
    )

    friends_by_appt = find_friends_in_appointments(visible, friends, client) or {}

    now = datetime.now()
    appt_data = []
    for appt in visible:
        sched = schedule_map.get(appt.name)
        appt_has_1rm = sched is not None and (
            has_1rm_exercise(sched.strength_specialty)
            or has_1rm_exercise(sched.warmup_mobility)
            or has_1rm_exercise(sched.metcon)
        )
        actual_start = datetime.combine(target_date, appt.date_start.time())
        appt_data.append({
            "id": appt.id_appointment,
            "name": appt.name,
            "date_start": target_date.isoformat(),
            "date_end": target_date.isoformat(),
            "time_start": appt.date_start.strftime("%H:%M"),
            "time_end": appt.date_end.strftime("%H:%M"),
            "spots_taken": appt.total_subscriptions,
            "spots_total": appt.max_subscriptions,
            "status": appt.status,
            "friends": friends_by_appt.get(appt.id_appointment, []) or [],
            "has_1rm": appt_has_1rm,
            "signup_open": is_signup_open(appt.name, actual_start),
            "is_past": actual_start < now,
        })

    return appt_data
