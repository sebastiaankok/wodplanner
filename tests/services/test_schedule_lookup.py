from datetime import date
from unittest.mock import patch

from wodplanner.models.schedule import Schedule
from wodplanner.services.schedule import ScheduleService
from wodplanner.services.schedule_lookup import match_schedule, match_schedules_for_date


class TestMatchSchedule:
    """Tests for the schedule_lookup.match_schedule function."""

    def test_service_exception_returns_none_with_debug_log(self, db_path):
        """Schedule service exception is swallowed, returns None, logs debug message."""
        svc = ScheduleService(db_path)

        with patch.object(svc, 'get_by_date_and_class', side_effect=RuntimeError("DB crash")):
            with patch("wodplanner.services.schedule_lookup.logger") as mock_logger:
                result = match_schedule(svc, "CrossFit", date(2026, 1, 5), gym_id=1)

        assert result is None
        mock_logger.debug.assert_called_once()
        assert "CrossFit" in mock_logger.debug.call_args[0][1]

    def test_direct_alias_hit(self, db_path):
        """When service finds a schedule, return it."""
        svc = ScheduleService(db_path)
        svc.add(Schedule(date=date(2026, 1, 5), class_type="CrossFit", metcon="21-15-9", gym_id=1))

        result = match_schedule(svc, "CrossFit", date(2026, 1, 5), gym_id=1)

        assert result is not None
        assert result.metcon == "21-15-9"

    def test_alias_resolution_via_service(self, db_path):
        """Alias lookup (e.g. Oly → Olympic Lifting) works through service."""
        svc = ScheduleService(db_path)
        svc.add(Schedule(date=date(2026, 1, 6), class_type="Olympic Lifting", metcon="C&J", gym_id=1))

        result = match_schedule(svc, "Oly", date(2026, 1, 6), gym_id=1)

        assert result is not None
        assert result.metcon == "C&J"

    def test_no_schedule_returns_none(self, db_path):
        """When no schedule exists for the date/class, return None."""
        svc = ScheduleService(db_path)

        result = match_schedule(svc, "CrossFit", date(2099, 1, 1), gym_id=1)

        assert result is None

    def test_gym_id_isolation(self, db_path):
        """Only return schedules matching the given gym_id."""
        svc = ScheduleService(db_path)
        svc.add(Schedule(date=date(2026, 1, 7), class_type="CrossFit", metcon="gym1", gym_id=1))
        svc.add(Schedule(date=date(2026, 1, 7), class_type="CrossFit", metcon="gym2", gym_id=2))

        result = match_schedule(svc, "CrossFit", date(2026, 1, 7), gym_id=2)

        assert result is not None
        assert result.metcon == "gym2"


class TestMatchSchedulesForDate:
    """Tests for the batch variant."""

    def test_returns_alias_keyed_dict(self, db_path):
        """All schedules for a date keyed by every known alias."""
        svc = ScheduleService(db_path)
        svc.add(Schedule(date=date(2026, 1, 8), class_type="Oly", metcon="C&J", gym_id=1))

        result = match_schedules_for_date(svc, date(2026, 1, 8), gym_id=1)

        assert "Olympic Lifting" in result
        assert "Oly" in result
        assert result["Olympic Lifting"] is result["Oly"]

    def test_empty_when_no_schedules(self, db_path):
        """Return empty dict when no schedules exist for the date."""
        svc = ScheduleService(db_path)

        result = match_schedules_for_date(svc, date(2099, 1, 1), gym_id=1)

        assert result == {}

    def test_service_exception_returns_empty_dict(self, db_path):
        """Schedule service exception is swallowed, returns empty dict."""
        svc = ScheduleService(db_path)

        with patch.object(svc, 'get_by_date', side_effect=RuntimeError("DB crash")):
            with patch("wodplanner.services.schedule_lookup.logger") as mock_logger:
                result = match_schedules_for_date(svc, date(2026, 1, 5), gym_id=1)

        assert result == {}
        mock_logger.debug.assert_called_once()
