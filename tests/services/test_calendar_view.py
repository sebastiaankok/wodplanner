"""Tests for services/calendar_view.py"""

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from wodplanner.models.friends import Friend
from wodplanner.services.calendar_view import (
    build_calendar_view,
    is_signup_open,
)

TZ = ZoneInfo("Europe/Amsterdam")


class TestIsSignupOpen:
    def test_cf101_signup_opens_14_weeks_before(self):
        appt_start = datetime(2026, 6, 1, 9, 0, tzinfo=TZ)
        result = is_signup_open("CF101", appt_start)
        expected = datetime.now(TZ) >= (appt_start - timedelta(weeks=14))
        assert result == expected

    def test_101_signup_opens_14_weeks_before(self):
        appt_start = datetime(2026, 6, 1, 9, 0, tzinfo=TZ)
        result = is_signup_open("101", appt_start)
        expected = datetime.now(TZ) >= (appt_start - timedelta(weeks=14))
        assert result == expected

    def test_regular_class_signup_opens_7_days_before(self):
        appt_start = datetime(2026, 6, 1, 9, 0, tzinfo=TZ)
        result = is_signup_open("CrossFit", appt_start)
        expected = datetime.now(TZ) >= (appt_start - timedelta(days=7))
        assert result == expected

    def test_oly_class_signup_opens_7_days_before(self):
        appt_start = datetime(2026, 6, 1, 9, 0, tzinfo=TZ)
        result = is_signup_open("Olympic Lifting", appt_start)
        expected = datetime.now(TZ) >= (appt_start - timedelta(days=7))
        assert result == expected

    def test_naive_datetime_gets_tz(self):
        appt_start = datetime(2026, 6, 1, 9, 0)  # naive
        result = is_signup_open("CrossFit", appt_start)
        appt_with_tz = appt_start.replace(tzinfo=TZ)
        expected = datetime.now(TZ) >= (appt_with_tz - timedelta(days=7))
        assert result == expected

    def test_past_appointment_returns_true(self):
        appt_start = datetime(2020, 1, 1, 9, 0, tzinfo=TZ)
        assert is_signup_open("CrossFit", appt_start) is True


class TestBuildCalendarView:
    def test_filters_hidden_types(self):
        session = MagicMock()
        session.user_id = 1
        session.gym_id = 1
        client = MagicMock()
        friends_service = MagicMock()
        schedule_service = MagicMock()

        appt = MagicMock()
        appt.id_appointment = 1
        appt.name = "Hidden Class"
        appt.date_start = datetime(2026, 1, 1, 9, 0)
        appt.date_end = datetime(2026, 1, 1, 10, 0)
        appt.total_subscriptions = 5
        appt.max_subscriptions = 20
        appt.status = "open"

        client.get_day_schedule.return_value = [appt]
        friends_service.get_all.return_value = []
        schedule_service.get_all_for_date.return_value = {}

        result = build_calendar_view(
            session, date(2026, 1, 1), client, friends_service, schedule_service, {"Hidden Class"}
        )
        assert len(result) == 0

    def test_builds_appointment_data(self):
        session = MagicMock()
        session.user_id = 1
        session.gym_id = 1
        client = MagicMock()
        friends_service = MagicMock()
        schedule_service = MagicMock()

        appt = MagicMock()
        appt.id_appointment = 1
        appt.name = "CrossFit"
        appt.date_start = datetime(2026, 1, 1, 9, 0)
        appt.date_end = datetime(2026, 1, 1, 10, 0)
        appt.total_subscriptions = 5
        appt.max_subscriptions = 20
        appt.status = "open"

        client.get_day_schedule.return_value = [appt]
        friends_service.get_all.return_value = []
        schedule_service.get_all_for_date.return_value = {}

        result = build_calendar_view(
            session, date(2026, 1, 1), client, friends_service, schedule_service, set()
        )
        assert len(result) == 1
        assert result[0]["id"] == 1
        assert result[0]["name"] == "CrossFit"
        assert result[0]["spots_taken"] == 5
        assert result[0]["spots_total"] == 20
        assert result[0]["status"] == "open"

    def test_adds_friend_info(self):
        session = MagicMock()
        session.user_id = 1
        session.gym_id = 1
        client = MagicMock()
        friends_service = MagicMock()
        schedule_service = MagicMock()

        appt = MagicMock()
        appt.id_appointment = 1
        appt.name = "CrossFit"
        appt.date_start = datetime(2026, 1, 1, 9, 0)
        appt.date_end = datetime(2026, 1, 1, 10, 0)
        appt.total_subscriptions = 1
        appt.max_subscriptions = 20
        appt.status = "open"

        friend = Friend(appuser_id=100, name="John", owner_user_id=1)

        client.get_day_schedule.return_value = [appt]
        friends_service.get_all.return_value = [friend]
        schedule_service.get_all_for_date.return_value = {}

        member = MagicMock()
        member.id_appuser = 100
        member.name = "John"
        client.get_appointment_members.return_value = ([member], None)

        result = build_calendar_view(
            session, date(2026, 1, 1), client, friends_service, schedule_service, set()
        )
        assert len(result) == 1
        assert len(result[0]["friends"]) == 1
        assert result[0]["friends"][0].name == "John"

    def test_adds_1rm_marker(self):
        session = MagicMock()
        session.user_id = 1
        session.gym_id = 1
        client = MagicMock()
        friends_service = MagicMock()
        schedule_service = MagicMock()

        appt = MagicMock()
        appt.id_appointment = 1
        appt.name = "CrossFit"
        appt.date_start = datetime(2026, 1, 1, 9, 0)
        appt.date_end = datetime(2026, 1, 1, 10, 0)
        appt.total_subscriptions = 5
        appt.max_subscriptions = 20
        appt.status = "open"

        sched = MagicMock()
        sched.strength_specialty = "1RM Back Squat"
        sched.warmup_mobility = None
        sched.metcon = None
        sched.class_type = "CrossFit"

        client.get_day_schedule.return_value = [appt]
        friends_service.get_all.return_value = []
        schedule_service.get_all_for_date.return_value = {"CrossFit": sched}

        result = build_calendar_view(
            session, date(2026, 1, 1), client, friends_service, schedule_service, set()
        )
        assert len(result) == 1
        assert result[0]["has_1rm"] is True
