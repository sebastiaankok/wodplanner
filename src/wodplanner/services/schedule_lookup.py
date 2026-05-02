"""Schedule lookup module — owns the Appointment ↔ Schedule matching rule."""

import logging
from datetime import date

from wodplanner.models.schedule import Schedule
from wodplanner.services.schedule import ScheduleService, get_all_class_aliases

logger = logging.getLogger(__name__)


def match_schedule(
    service: ScheduleService,
    class_type: str,
    target_date: date,
    gym_id: int | None = None,
) -> Schedule | None:
    """Match a schedule for a given class type and date.

    Wraps the service lookup with exception swallowing so a schedule-service
    failure never aborts the caller (e.g. calendar rendering, sync).
    """
    try:
        return service.get_by_date_and_class(target_date, class_type, gym_id=gym_id)
    except Exception:
        logger.debug("Schedule lookup failed for %s on %s", class_type, target_date)
        return None


def match_schedules_for_date(
    service: ScheduleService,
    target_date: date,
    gym_id: int | None = None,
) -> dict[str, Schedule]:
    """Batch variant — all schedules for a date keyed by every known alias.

    Suitable for calendar-day rendering where multiple appointments need
    O(1) schedule lookups.
    """
    try:
        schedules = service.get_by_date(target_date, gym_id)
        result: dict[str, Schedule] = {}
        for s in schedules:
            result[s.class_type] = s
            for alias in get_all_class_aliases(s.class_type):
                result[alias] = s
        return result
    except Exception:
        logger.debug("Batch schedule lookup failed for %s", target_date)
        return {}
