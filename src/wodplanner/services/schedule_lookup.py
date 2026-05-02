"""Schedule lookup module — owns Appointment ↔ Schedule matching end-to-end.

Centralises alias map lookup, normalize_class_name fallback, and exception
swallowing with debug logging so callers don't repeat the pattern.
"""

import logging
from datetime import date

from wodplanner.models.schedule import Schedule
from wodplanner.services.schedule import ScheduleService, normalize_class_name

logger = logging.getLogger(__name__)


def match_schedule(
    class_type: str,
    target_date: date,
    gym_id: int | None,
    schedule_service: ScheduleService | None = None,
) -> Schedule | None:
    """Find a Schedule that matches an Appointment's Class Type and date.

    Tries direct alias lookup first, then falls back to normalising the class
    name to its canonical form. Swallows exceptions from the schedule service
    and returns None with a debug log.
    """
    if not schedule_service:
        return None
    try:
        schedule_map = schedule_service.get_all_for_date(target_date, gym_id=gym_id)
    except Exception:
        logger.debug(
            "Schedule lookup failed for class_type=%r date=%s", class_type, target_date
        )
        return None

    sched = schedule_map.get(class_type)
    if sched is not None:
        return sched

    normalized = normalize_class_name(class_type)
    if normalized != class_type:
        sched = schedule_map.get(normalized)
        if sched is not None:
            return sched

    return None


def match_schedules_for_date(
    target_date: date,
    gym_id: int | None,
    schedule_service: ScheduleService | None = None,
) -> dict[str, Schedule]:
    """Fetch all schedules for a date — batch variant for calendar-day rendering.

    Returns every known alias mapped to its Schedule so callers can do O(1)
    lookups by API class name. Swallows exceptions and returns an empty dict.
    """
    if not schedule_service:
        return {}
    try:
        return schedule_service.get_all_for_date(target_date, gym_id=gym_id)
    except Exception:
        logger.debug(
            "Schedule batch lookup failed for date=%s", target_date
        )
        return {}
