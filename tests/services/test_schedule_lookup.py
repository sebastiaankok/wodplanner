"""Tests for services/schedule_lookup.py — Appointment ↔ Schedule matching."""

from datetime import date
from unittest.mock import MagicMock, patch

from wodplanner.models.schedule import Schedule


def _make_schedule(class_type="CrossFit", sched_date=None):
    return Schedule(
        id=1,
        gym_id=2495,
        date=sched_date or date(2026, 5, 1),
        class_type=class_type,
        warmup_mobility=None,
        strength_specialty=None,
        metcon=None,
    )


def _make_schedule_service(schedules_for_date=None):
    """Create a mock ScheduleService that returns schedules keyed by alias."""
    svc = MagicMock()
    svc.get_all_for_date.return_value = schedules_for_date or {}
    return svc


class TestMatchSchedule:
    def test_alias_hit_returns_schedule(self):
        from wodplanner.services.schedule_lookup import match_schedule

        sched = _make_schedule("CrossFit")
        schedule_service = _make_schedule_service({"CrossFit": sched})

        result = match_schedule(
            "CrossFit", date(2026, 5, 1), gym_id=2495, schedule_service=schedule_service
        )
        assert result is sched

    def test_alias_hit_via_mapping_returns_schedule(self):
        from wodplanner.services.schedule_lookup import match_schedule

        """API reports 'Oly' but schedule stored as 'Olympic Lifting'. Alias map covers it."""
        sched = _make_schedule("Olympic Lifting")
        schedule_service = _make_schedule_service({
            "Olympic Lifting": sched,
            "Oly": sched,  # alias already in map from get_all_for_date
        })

        result = match_schedule(
            "Oly", date(2026, 5, 1), gym_id=2495, schedule_service=schedule_service
        )
        assert result is sched

    def test_normalize_fallback_hit(self):
        from wodplanner.services.schedule_lookup import match_schedule

        """API reports 'Boxing' (alias) but map only has canonical 'Boxing Class'.
        normalize_class_name resolves the alias to find the schedule."""
        sched = _make_schedule("Boxing Class")
        # Simulate schedule_map that lacks the alias key (edge case / defensive coverage)
        schedule_service = _make_schedule_service({
            "Boxing Class": sched,
        })

        result = match_schedule(
            "Boxing", date(2026, 5, 1), gym_id=2495, schedule_service=schedule_service
        )
        assert result is sched

    def test_miss_returns_none(self):
        from wodplanner.services.schedule_lookup import match_schedule

        schedule_service = _make_schedule_service({})

        result = match_schedule(
            "NonExistent", date(2026, 5, 1), gym_id=2495, schedule_service=schedule_service
        )
        assert result is None

    def test_schedule_service_exception_returns_none(self):
        from wodplanner.services.schedule_lookup import match_schedule

        schedule_service = MagicMock()
        schedule_service.get_all_for_date.side_effect = Exception("DB connection lost")

        with patch("wodplanner.services.schedule_lookup.logger") as mock_logger:
            result = match_schedule(
                "CrossFit", date(2026, 5, 1), gym_id=2495, schedule_service=schedule_service
            )
        assert result is None
        mock_logger.debug.assert_called_once()

    def test_no_schedule_service_returns_none(self):
        from wodplanner.services.schedule_lookup import match_schedule

        result = match_schedule(
            "CrossFit", date(2026, 5, 1), gym_id=2495, schedule_service=None
        )
        assert result is None


class TestMatchSchedulesForDate:
    def test_returns_all_schedules_for_date(self):
        from wodplanner.services.schedule_lookup import match_schedules_for_date

        cf = _make_schedule("CrossFit")
        oly = _make_schedule("Olympic Lifting")
        schedule_service = _make_schedule_service({
            "CrossFit": cf,
            "CF101": cf,  # alias
            "Olympic Lifting": oly,
            "Oly": oly,  # alias
        })

        result = match_schedules_for_date(
            date(2026, 5, 1), gym_id=2495, schedule_service=schedule_service
        )
        assert result["CrossFit"] is cf
        assert result["Olympic Lifting"] is oly

    def test_empty_when_no_schedules(self):
        from wodplanner.services.schedule_lookup import match_schedules_for_date

        schedule_service = _make_schedule_service({})

        result = match_schedules_for_date(
            date(2026, 5, 1), gym_id=2495, schedule_service=schedule_service
        )
        assert result == {}

    def test_schedule_service_exception_returns_empty(self):
        from wodplanner.services.schedule_lookup import match_schedules_for_date

        schedule_service = MagicMock()
        schedule_service.get_all_for_date.side_effect = Exception("DB error")

        with patch("wodplanner.services.schedule_lookup.logger") as mock_logger:
            result = match_schedules_for_date(
                date(2026, 5, 1), gym_id=2495, schedule_service=schedule_service
            )
        assert result == {}
        mock_logger.debug.assert_called_once()

    def test_no_schedule_service_returns_empty(self):
        from wodplanner.services.schedule_lookup import match_schedules_for_date

        result = match_schedules_for_date(
            date(2026, 5, 1), gym_id=2495, schedule_service=None
        )
        assert result == {}
