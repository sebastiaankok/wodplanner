"""Tests for services/benchmark.py — benchmark WOD detection and service."""

from datetime import datetime
from zoneinfo import ZoneInfo

from wodplanner.services.benchmark import (
    BenchmarkService,
    extract_benchmark_names,
    find_benchmark_in_schedule,
)


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

    def test_no_match_for_partial_word(self):
        names = ["Eva", "Grace", "Nancy"]
        result = find_benchmark_in_schedule(
            schedule_texts=["Coach: Evangelina | Warm-up: 400m run"],
            benchmark_names=names,
        )
        assert result is None

    def test_partial_word_does_not_shadow_real_match(self):
        names = ["Eva", "Fran"]
        result = find_benchmark_in_schedule(
            schedule_texts=["Coach: Evangelina | Metcon: Fran"],
            benchmark_names=names,
        )
        assert result == "Fran"


class TestExtractBenchmarkNames:
    def test_empty_text_returns_empty(self):
        assert extract_benchmark_names(None) == []
        assert extract_benchmark_names("") == []

    def test_quoted_benchmark_extracts_name(self):
        text = "MetCon\nBenchmark \u2018Cindy\u2019\n20min AMRAP"
        result = extract_benchmark_names(text)
        assert result == ["Cindy"]

    def test_unquoted_benchmark_extracts_name(self):
        text = "MetCon\nBenchmark Battle of the Bull 22.3\n3 Rounds For Time"
        result = extract_benchmark_names(text)
        assert result == ["Battle of the Bull 22.3"]

    def test_multiple_benchmarks_in_text(self):
        text = "Benchmark \u2018Nasty Girls\u2019 and Benchmark \u2018Helen\u2019"
        result = extract_benchmark_names(text)
        assert result == ["Nasty Girls", "Helen"]

    def test_no_benchmark_prefix_returns_empty(self):
        text = "Just a normal metcon with no benchmarks"
        result = extract_benchmark_names(text)
        assert result == []

    def test_benchmark_in_mobility_column_ignored(self):
        text = "Mobility: Banded Shoulder Dislocation"
        result = extract_benchmark_names(text)
        assert result == []

    def test_benchmark_with_trailing_punctuation_stripped(self):
        text = "Benchmark \u2018Hero DT\u2019: For Time"
        result = extract_benchmark_names(text)
        assert result == ["Hero DT"]


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
    def test_add_and_get_results(self, db_path, make_user):
        make_user(1)
        svc = BenchmarkService(db_path)
        svc.add_result(user_id=1, benchmark_name="Fran", time_seconds=180, is_rx=True, recorded_at="2026-05-05")
        results = svc.get_results_for_benchmark(user_id=1, benchmark_name="Fran")
        assert len(results) == 1
        assert results[0].time_seconds == 180
        assert results[0].is_rx is True

    def test_results_ordered_by_date_desc(self, db_path, make_user):
        make_user(1)
        svc = BenchmarkService(db_path)
        svc.add_result(user_id=1, benchmark_name="Fran", time_seconds=300, is_rx=True, recorded_at="2026-05-04")
        svc.add_result(user_id=1, benchmark_name="Fran", time_seconds=180, is_rx=True, recorded_at="2026-05-05")
        results = svc.get_results_for_benchmark(user_id=1, benchmark_name="Fran")
        assert results[0].recorded_at == "2026-05-05"
        assert results[1].recorded_at == "2026-05-04"

    def test_scoped_by_user(self, db_path, make_user):
        make_user(1, 2)
        svc = BenchmarkService(db_path)
        svc.add_result(user_id=1, benchmark_name="Fran", time_seconds=180, is_rx=True, recorded_at="2026-05-05")
        results = svc.get_results_for_benchmark(user_id=2, benchmark_name="Fran")
        assert len(results) == 0

    def test_scoped_by_benchmark_name(self, db_path, make_user):
        make_user(1)
        svc = BenchmarkService(db_path)
        svc.add_result(user_id=1, benchmark_name="Fran", time_seconds=180, is_rx=True, recorded_at="2026-05-05")
        svc.add_result(user_id=1, benchmark_name="Helen", time_seconds=600, is_rx=True, recorded_at="2026-05-05")
        results = svc.get_results_for_benchmark(user_id=1, benchmark_name="Fran")
        assert len(results) == 1
        assert results[0].benchmark_name == "Fran"

    def test_delete_result(self, db_path, make_user):
        make_user(1)
        svc = BenchmarkService(db_path)
        r = svc.add_result(user_id=1, benchmark_name="Fran", time_seconds=180, is_rx=True, recorded_at="2026-05-05")
        svc.delete_result(user_id=1, result_id=r.id)
        results = svc.get_results_for_benchmark(user_id=1, benchmark_name="Fran")
        assert len(results) == 0

    def test_delete_scoped_by_user(self, db_path, make_user):
        make_user(1, 2)
        svc = BenchmarkService(db_path)
        r = svc.add_result(user_id=1, benchmark_name="Fran", time_seconds=180, is_rx=True, recorded_at="2026-05-05")
        svc.delete_result(user_id=2, result_id=r.id)
        results = svc.get_results_for_benchmark(user_id=1, benchmark_name="Fran")
        assert len(results) == 1

    def test_add_result_returns_model_with_id(self, db_path, make_user):
        make_user(1)
        svc = BenchmarkService(db_path)
        r = svc.add_result(user_id=1, benchmark_name="Fran", time_seconds=180, is_rx=True, recorded_at="2026-05-05")
        assert r.id is not None
        assert r.user_id == 1

    def test_update_result(self, db_path, make_user):
        make_user(1)
        svc = BenchmarkService(db_path)
        r = svc.add_result(user_id=1, benchmark_name="Fran", time_seconds=180, is_rx=True, recorded_at="2026-05-05")
        updated = svc.update_result(user_id=1, result_id=r.id, benchmark_name="Helen", time_seconds=240, is_rx=False, recorded_at="2026-06-01")
        assert updated is True

        result = svc.get_result(user_id=1, result_id=r.id)
        assert result is not None
        assert result.benchmark_name == "Helen"
        assert result.time_seconds == 240
        assert result.is_rx is False
        assert result.recorded_at == "2026-06-01"

    def test_update_result_scoped_by_user(self, db_path, make_user):
        make_user(1, 2)
        svc = BenchmarkService(db_path)
        r = svc.add_result(user_id=1, benchmark_name="Fran", time_seconds=180, is_rx=True, recorded_at="2026-05-05")
        updated = svc.update_result(user_id=2, result_id=r.id, benchmark_name="Helen", time_seconds=240, is_rx=False, recorded_at="2026-06-01")
        assert updated is False
