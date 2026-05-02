"""Schedule lookup module — owns the Appointment ↔ Schedule matching rule."""

import logging
from datetime import date

from wodplanner.models.schedule import Schedule
from wodplanner.services.schedule import ScheduleService

logger = logging.getLogger(__name__)


def match_schedule(
    service: ScheduleService,
    class_type: str,
    target_date: date,
    gym_id: int | None = None,
    extra_log: str | None = None,
) -> Schedule | None:
    """Match a schedule for a given class type and date.

    Wraps the service lookup with exception swallowing so a schedule-service
    failure never aborts the caller (e.g. calendar rendering, sync).

    Args:
        extra_log: Optional context string appended to error logs (e.g. appointment ID).
    """
    try:
        return service.get_by_date_and_class(target_date, class_type, gym_id=gym_id)
    except Exception:
        context = f" ({extra_log})" if extra_log else ""
        logger.warning(
            "Schedule lookup failed for %s on %s%s",
            class_type, target_date, context,
            exc_info=True,
        )
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
        return service.get_all_for_date(target_date, gym_id)
    except Exception:
        logger.warning("Batch schedule lookup failed for %s", target_date, exc_info=True)
        return {}
