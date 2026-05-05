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


class TestBenchmarkResultModel:
    def test_can_create_result(self):
        from wodplanner.models.benchmark import BenchmarkResult

        r = BenchmarkResult(
            user_id=42,
            benchmark_name="Fran",
            time_seconds=180,
            is_rx=True,
            recorded_at="2026-05-05",
        )
        assert r.user_id == 42
        assert r.benchmark_name == "Fran"
        assert r.time_seconds == 180
        assert r.is_rx is True
        assert r.recorded_at == "2026-05-05"


class TestBenchmarkResultService:
    def test_add_and_get_results(self, db_path):
        svc = BenchmarkService(db_path)
        svc.add_result(user_id=1, benchmark_name="Fran", time_seconds=180, is_rx=True, recorded_at="2026-05-05")
        results = svc.get_results_for_benchmark(user_id=1, benchmark_name="Fran")
        assert len(results) == 1
        assert results[0].time_seconds == 180
        assert results[0].is_rx is True

    def test_results_ordered_by_date_desc(self, db_path):
        svc = BenchmarkService(db_path)
        svc.add_result(user_id=1, benchmark_name="Fran", time_seconds=300, is_rx=True, recorded_at="2026-05-04")
        svc.add_result(user_id=1, benchmark_name="Fran", time_seconds=180, is_rx=True, recorded_at="2026-05-05")
        results = svc.get_results_for_benchmark(user_id=1, benchmark_name="Fran")
        assert results[0].recorded_at == "2026-05-05"
        assert results[1].recorded_at == "2026-05-04"

    def test_scoped_by_user(self, db_path):
        svc = BenchmarkService(db_path)
        svc.add_result(user_id=1, benchmark_name="Fran", time_seconds=180, is_rx=True, recorded_at="2026-05-05")
        results = svc.get_results_for_benchmark(user_id=2, benchmark_name="Fran")
        assert len(results) == 0

    def test_scoped_by_benchmark_name(self, db_path):
        svc = BenchmarkService(db_path)
        svc.add_result(user_id=1, benchmark_name="Fran", time_seconds=180, is_rx=True, recorded_at="2026-05-05")
        svc.add_result(user_id=1, benchmark_name="Helen", time_seconds=600, is_rx=True, recorded_at="2026-05-05")
        results = svc.get_results_for_benchmark(user_id=1, benchmark_name="Fran")
        assert len(results) == 1
        assert results[0].benchmark_name == "Fran"

    def test_delete_result(self, db_path):
        svc = BenchmarkService(db_path)
        r = svc.add_result(user_id=1, benchmark_name="Fran", time_seconds=180, is_rx=True, recorded_at="2026-05-05")
        svc.delete_result(user_id=1, result_id=r.id)
        results = svc.get_results_for_benchmark(user_id=1, benchmark_name="Fran")
        assert len(results) == 0

    def test_delete_scoped_by_user(self, db_path):
        svc = BenchmarkService(db_path)
        r = svc.add_result(user_id=1, benchmark_name="Fran", time_seconds=180, is_rx=True, recorded_at="2026-05-05")
        svc.delete_result(user_id=2, result_id=r.id)
        results = svc.get_results_for_benchmark(user_id=1, benchmark_name="Fran")
        assert len(results) == 1

    def test_add_result_returns_model_with_id(self, db_path):
        svc = BenchmarkService(db_path)
        r = svc.add_result(user_id=1, benchmark_name="Fran", time_seconds=180, is_rx=True, recorded_at="2026-05-05")
        assert r.id is not None
        assert r.user_id == 1
