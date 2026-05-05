"""Tests for services/benchmark.py — benchmark WOD detection and service."""

from datetime import datetime
from zoneinfo import ZoneInfo

from wodplanner.services.benchmark import BenchmarkService, find_benchmark_in_schedule


class TestFindBenchmarkInSchedule:
    def test_finds_murph_in_metcon(self):
        names = ["Murph", "Fran", "Helen"]
        result = find_benchmark_in_schedule(
            schedule_texts=["Metcon: Murph for time"],
            benchmark_names=names,
        )
        assert result == "Murph"

    def test_returns_none_when_no_match(self):
        names = ["Murph", "Fran", "Helen"]
        result = find_benchmark_in_schedule(
            schedule_texts=["Metcon: some other workout"],
            benchmark_names=names,
        )
        assert result is None

    def test_case_insensitive_matching(self):
        names = ["Murph", "Fran", "Helen"]
        result = find_benchmark_in_schedule(
            schedule_texts=["Metcon: murph for time"],
            benchmark_names=names,
        )
        assert result == "Murph"

    def test_handles_none_texts(self):
        names = ["Murph", "Fran"]
        result = find_benchmark_in_schedule(
            schedule_texts=[None, "", None],
            benchmark_names=names,
        )
        assert result is None

    def test_returns_first_match_in_list_order(self):
        names = ["Fran", "Helen", "Murph"]
        result = find_benchmark_in_schedule(
            schedule_texts=["Metcon: Helen and Murph for time"],
            benchmark_names=names,
        )
        assert result == "Helen"

    def test_scans_multiple_fields(self):
        names = ["Fran", "Helen", "Cindy"]
        result = find_benchmark_in_schedule(
            schedule_texts=["Warm-up: light jog", "", "Strength: 5x5", "Metcon: Cindy"],
            benchmark_names=names,
        )
        assert result == "Cindy"


class TestDayCardEnrichment:
    def test_benchmark_enrichment_adds_fields(self):
        """DayCard gets has_benchmark and benchmark_name when schedule matches."""
        from datetime import date

        from wodplanner.models.calendar import Appointment
        from wodplanner.models.schedule import Schedule
        from wodplanner.services.day_card import build_day_cards

        appt = Appointment(
            id_appointment=1,
            id_appointment_type=1,
            name="CrossFit",
            date_start=datetime(2026, 6, 15, 9, 0),
            date_end=datetime(2026, 6, 15, 10, 0),
            max_subscriptions=20,
            total_subscriptions=5,
            status="open",
        )
        sched = Schedule(
            date=date(2026, 6, 15),
            class_type="CrossFit",
            metcon="Murph for time",
        )
        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={},
            schedule_by_class_type={"CrossFit": sched},
            now=datetime(2026, 6, 10, 12, 0, tzinfo=ZoneInfo("Europe/Amsterdam")),
            benchmark_names=["Murph", "Fran", "Helen"],
        )
        card = result[0]
        assert card.has_benchmark is True
        assert card.benchmark_name == "Murph"

    def test_no_benchmark_when_no_match(self):
        from datetime import date

        from wodplanner.models.calendar import Appointment
        from wodplanner.models.schedule import Schedule
        from wodplanner.services.day_card import build_day_cards

        appt = Appointment(
            id_appointment=1,
            id_appointment_type=1,
            name="CrossFit",
            date_start=datetime(2026, 6, 15, 9, 0),
            date_end=datetime(2026, 6, 15, 10, 0),
            max_subscriptions=20,
            total_subscriptions=5,
            status="open",
        )
        sched = Schedule(
            date=date(2026, 6, 15),
            class_type="CrossFit",
            metcon="Some other workout",
        )
        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={},
            schedule_by_class_type={"CrossFit": sched},
            now=datetime(2026, 6, 10, 12, 0, tzinfo=ZoneInfo("Europe/Amsterdam")),
            benchmark_names=["Murph", "Fran", "Helen"],
        )
        card = result[0]
        assert card.has_benchmark is False
        assert card.benchmark_name is None

    def test_no_schedule_no_benchmark(self):
        from wodplanner.models.calendar import Appointment
        from wodplanner.services.day_card import build_day_cards

        appt = Appointment(
            id_appointment=1,
            id_appointment_type=1,
            name="CrossFit",
            date_start=datetime(2026, 6, 15, 9, 0),
            date_end=datetime(2026, 6, 15, 10, 0),
            max_subscriptions=20,
            total_subscriptions=5,
            status="open",
        )
        result = build_day_cards(
            appointments=[appt],
            friends_by_appt_id={},
            schedule_by_class_type={},
            now=datetime(2026, 6, 10, 12, 0, tzinfo=ZoneInfo("Europe/Amsterdam")),
            benchmark_names=["Murph", "Fran"],
        )
        card = result[0]
        assert card.has_benchmark is False
        assert card.benchmark_name is None


class TestBenchmarkService:
    def test_get_benchmark_list_returns_seeded_names(self, db_path):
        svc = BenchmarkService(db_path)
        names = svc.get_benchmark_list()
        assert len(names) >= 28
        assert "Murph" in names
        assert "Fran" in names
        assert "Cindy" in names

    def test_add_benchmark_wod(self, db_path):
        svc = BenchmarkService(db_path)
        result = svc.add_benchmark_wod("Fight Gone Bad", "Benchmark")
        assert result is True

        names = svc.get_benchmark_list()
        assert "Fight Gone Bad" in names

    def test_add_benchmark_wod_duplicate_returns_false(self, db_path):
        svc = BenchmarkService(db_path)
        svc.add_benchmark_wod("Test Benchmark", "The Girls")
        result = svc.add_benchmark_wod("Test Benchmark", "Hero")
        assert result is False
