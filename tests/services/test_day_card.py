"""Tests for services/day_card.py — DayCard model and build_day_cards builder."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from wodplanner.models.calendar import Appointment
from wodplanner.models.friends import Friend
from wodplanner.models.schedule import Schedule
from wodplanner.services.day_card import build_day_cards

TZ = ZoneInfo("Europe/Amsterdam")


def _make_appointment(
    appt_id: int = 1,
    name: str = "CrossFit",
    hour_start: int = 9,
    hour_end: int = 10,
    total_subs: int = 5,
    max_subs: int = 20,
    status: str = "open",
) -> Appointment:
    return Appointment(
        id_appointment=appt_id,
        id_appointment_type=1,
        name=name,
        date_start=datetime(2026, 6, 15, hour_start, 0),
        date_end=datetime(2026, 6, 15, hour_end, 0),
        max_subscriptions=max_subs,
        total_subscriptions=total_subs,
        status=status,
    )


class TestEmptyInputs:
    def test_empty_appointments_returns_empty_list(self):
        result = build_day_cards(
            appointments=[],
            friends_by_appt_id={},
            schedule_by_class_type={},
            now=datetime.now(TZ),
        )
        assert result == []


class TestBuildDayCardsBasic:
    def test_builds_all_fields_from_appointment(self):
        appt = _make_appointment()
        friend = Friend(appuser_id=100, name="John", owner_user_id=1)

        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={1: [friend]},
            schedule_by_class_type={},
            now=datetime(2026, 1, 1, 12, 0, tzinfo=TZ),
        )

        assert len(result) == 1
        card = result[0]
        assert card.id == 1
        assert card.name == "CrossFit"
        assert card.time_start == "09:00"
        assert card.time_end == "10:00"
        assert card.spots_taken == 5
        assert card.spots_total == 20
        assert card.status == "open"
        assert card.date_start == "2026-06-15"
        assert card.date_end == "2026-06-15"
        assert card.friends == [friend]


class TestSignupWindow:
    def test_regular_class_signup_opens_7_days_before(self):
        """Regular class opens sign-up 7 days before start."""
        appt = _make_appointment(hour_start=9, hour_end=10)
        now = datetime(2026, 6, 10, 12, 0, tzinfo=TZ)

        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={},
            schedule_by_class_type={},
            now=now,
        )
        assert result[0].signup_open is True

    def test_regular_class_signup_not_open_8_days_before(self):
        """Regular class sign-up not open 8 days before start."""
        appt = _make_appointment(hour_start=9, hour_end=10)
        now = datetime(2026, 6, 7, 8, 0, tzinfo=TZ)

        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={},
            schedule_by_class_type={},
            now=now,
        )
        assert result[0].signup_open is False

    def test_cf101_signup_opens_14_weeks_before(self):
        """CF101 class opens sign-up 14 weeks before start."""
        appt = _make_appointment(name="CF101 Basics", hour_start=9, hour_end=10)
        signup_open_time = datetime(2026, 6, 15, 9, 0, tzinfo=TZ) - timedelta(weeks=14)
        now = signup_open_time + timedelta(hours=1)

        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={},
            schedule_by_class_type={},
            now=now,
        )
        assert result[0].signup_open is True

    def test_101_signup_opens_14_weeks_before(self):
        """Class with '101' in name opens sign-up 14 weeks before start."""
        appt = _make_appointment(name="Onboarding 101", hour_start=9, hour_end=10)
        signup_open_time = datetime(2026, 6, 15, 9, 0, tzinfo=TZ) - timedelta(weeks=14)
        now = signup_open_time + timedelta(hours=1)

        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={},
            schedule_by_class_type={},
            now=now,
        )
        assert result[0].signup_open is True

    def test_cf101_signup_not_open_14_weeks_plus_1_day_before(self):
        """CF101 sign-up not open 14 weeks + 1 day before start."""
        appt = _make_appointment(name="CF101", hour_start=9, hour_end=10)
        signup_open_time = datetime(2026, 6, 15, 9, 0, tzinfo=TZ) - timedelta(weeks=14)
        now = signup_open_time - timedelta(days=1)

        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={},
            schedule_by_class_type={},
            now=now,
        )
        assert result[0].signup_open is False

    def test_past_appointment_signup_open(self):
        """Past appointment always has signup_open True."""
        appt = _make_appointment(hour_start=9, hour_end=10)
        appt.date_start = datetime(2020, 1, 1, 9, 0)
        appt.date_end = datetime(2020, 1, 1, 10, 0)
        now = datetime(2026, 1, 1, 12, 0, tzinfo=TZ)

        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={},
            schedule_by_class_type={},
            now=now,
        )
        assert result[0].signup_open is True


class TestOneRMFlag:
    def _make_schedule(self, warmup=None, strength=None, metcon=None) -> Schedule:
        return Schedule(
            date=date(2026, 6, 15),
            class_type="CrossFit",
            warmup_mobility=warmup,
            strength_specialty=strength,
            metcon=metcon,
        )

    def test_1rm_in_warmup(self):
        appt = _make_appointment()
        sched = self._make_schedule(warmup="1RM Snatch")
        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={},
            schedule_by_class_type={"CrossFit": sched},
            now=datetime(2026, 6, 10, tzinfo=TZ),
        )
        assert result[0].has_1rm is True

    def test_1rm_in_strength(self):
        appt = _make_appointment()
        sched = self._make_schedule(strength="1RM Back Squat")
        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={},
            schedule_by_class_type={"CrossFit": sched},
            now=datetime(2026, 6, 10, tzinfo=TZ),
        )
        assert result[0].has_1rm is True

    def test_1rm_in_metcon(self):
        appt = _make_appointment()
        sched = self._make_schedule(metcon="5x 1RM Clean & Jerk")
        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={},
            schedule_by_class_type={"CrossFit": sched},
            now=datetime(2026, 6, 10, tzinfo=TZ),
        )
        assert result[0].has_1rm is True

    def test_1rm_in_multiple_sections(self):
        appt = _make_appointment()
        sched = self._make_schedule(warmup="1RM Snatch", strength="1RM Back Squat")
        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={},
            schedule_by_class_type={"CrossFit": sched},
            now=datetime(2026, 6, 10, tzinfo=TZ),
        )
        assert result[0].has_1rm is True

    def test_no_1rm(self):
        appt = _make_appointment()
        sched = self._make_schedule(warmup="Jumping Jacks", strength="3x5 Squat", metcon="EMOM 20")
        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={},
            schedule_by_class_type={"CrossFit": sched},
            now=datetime(2026, 6, 10, tzinfo=TZ),
        )
        assert result[0].has_1rm is False

    def test_percentage_reference_not_flagged(self):
        """80% 1RM should NOT trigger the flag."""
        appt = _make_appointment()
        sched = self._make_schedule(strength="5x5 @ 80% 1RM")
        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={},
            schedule_by_class_type={"CrossFit": sched},
            now=datetime(2026, 6, 10, tzinfo=TZ),
        )
        assert result[0].has_1rm is False

    def test_no_schedule_returns_false(self):
        appt = _make_appointment()
        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={},
            schedule_by_class_type={},
            now=datetime(2026, 6, 10, tzinfo=TZ),
        )
        assert result[0].has_1rm is False


class TestIsPast:
    def test_future_appointment_not_past(self):
        appt = _make_appointment()
        now = datetime(2026, 6, 14, 12, 0, tzinfo=TZ)

        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={},
            schedule_by_class_type={},
            now=now,
        )
        assert result[0].is_past is False

    def test_past_appointment_is_past(self):
        appt = _make_appointment()
        now = datetime(2026, 6, 15, 12, 0, tzinfo=TZ)

        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={},
            schedule_by_class_type={},
            now=now,
        )
        assert result[0].is_past is True

    def test_appointment_at_exact_now_is_past(self):
        appt = _make_appointment()
        now = datetime(2026, 6, 15, 9, 0, tzinfo=TZ)

        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={},
            schedule_by_class_type={},
            now=now,
        )
        assert result[0].is_past is False


class TestFriends:
    def test_friends_carried_through(self):
        appt = _make_appointment()
        friend1 = Friend(appuser_id=100, name="John", owner_user_id=1)
        friend2 = Friend(appuser_id=101, name="Jane", owner_user_id=1)

        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={1: [friend1, friend2]},
            schedule_by_class_type={},
            now=datetime(2026, 1, 1, tzinfo=TZ),
        )
        assert len(result[0].friends) == 2
        assert result[0].friends[0].name == "John"
        assert result[0].friends[1].name == "Jane"

    def test_no_friends_returns_empty_list(self):
        appt = _make_appointment()

        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={},
            schedule_by_class_type={},
            now=datetime(2026, 1, 1, tzinfo=TZ),
        )
        assert result[0].friends == []

    def test_none_friends_resolved_to_empty_list(self):
        appt = _make_appointment()

        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={1: None},  # type: ignore[arg-type]
            schedule_by_class_type={},
            now=datetime(2026, 1, 1, tzinfo=TZ),
        )
        assert result[0].friends == []
