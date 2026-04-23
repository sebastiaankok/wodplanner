"""Shared calendar view builder — used by calendar_page and calendar_day_partial."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from wodplanner.api.client import WodAppClient
from wodplanner.models.auth import AuthSession
from wodplanner.models.calendar import Appointment
from wodplanner.services.friends import FriendsService
from wodplanner.services.one_rep_max import has_1rm_exercise
from wodplanner.services.schedule import ScheduleService, normalize_class_name

logger = logging.getLogger(__name__)

_TZ = ZoneInfo("Europe/Amsterdam")
_MEMBERS_CONCURRENCY = 5


def is_signup_open(appt_name: str, appt_start: datetime) -> bool:
    now = datetime.now(_TZ)
    appt_start_tz = appt_start.replace(tzinfo=_TZ) if appt_start.tzinfo is None else appt_start
    if "CF101" in appt_name or "101" in appt_name:
        signup_opens = appt_start_tz - timedelta(weeks=14)
    else:
        signup_opens = appt_start_tz - timedelta(days=7)
    return now >= signup_opens


def _fetch_friends_in_appt(
    client: WodAppClient,
    appt: Appointment,
    friend_ids: set[int],
    friends_map: dict,
) -> tuple[int, list[dict]]:
    try:
        members, _ = client.get_appointment_members(
            appt.id_appointment, appt.date_start, appt.date_end,
            expected_total=appt.total_subscriptions,
        )
        friends = []
        for member in members:
            if member.id_appuser in friend_ids:
                friend = friends_map.get(member.id_appuser)
                friends.append({"id": member.id_appuser, "name": friend.name if friend else member.name})
        return appt.id_appointment, friends
    except Exception as exc:
        logger.warning("Failed to fetch members for appointment %s: %s", appt.id_appointment, exc)
        return appt.id_appointment, []


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

    friend_ids = friends_service.get_appuser_ids(session.user_id)
    friends_map = {f.appuser_id: f for f in friends_service.get_all(session.user_id)}

    schedule_map = schedule_service.get_all_for_date(target_date, gym_id=session.gym_id)

    friends_by_appt: dict[int, list[dict]] = {}
    if friend_ids:
        with ThreadPoolExecutor(max_workers=_MEMBERS_CONCURRENCY) as pool:
            futures = {
                pool.submit(_fetch_friends_in_appt, client, appt, friend_ids, friends_map): appt
                for appt in visible
            }
            for future in as_completed(futures):
                appt_id, friends_list = future.result()
                friends_by_appt[appt_id] = friends_list

    now = datetime.now()
    appt_data = []
    for appt in visible:
        sched = schedule_map.get(appt.name) or schedule_map.get(normalize_class_name(appt.name))
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
            "friends": friends_by_appt.get(appt.id_appointment, []),
            "has_1rm": appt_has_1rm,
            "signup_open": is_signup_open(appt.name, actual_start),
            "is_past": actual_start < now,
        })

    return appt_data
