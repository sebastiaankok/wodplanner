"""Tests for cli/import_schedule.py main()."""

from datetime import date
from unittest.mock import patch

import pytest

from wodplanner.cli import import_schedule
from wodplanner.models.schedule import Schedule


def _schedule() -> Schedule:
    return Schedule(
        date=date(2026, 4, 25),
        class_type="CrossFit",
        warmup_mobility="warmup",
        strength_specialty="1rm Back Squat",
        metcon="21-15-9 thrusters",
    )


class TestImportScheduleMain:
    def test_missing_pdf_exits_1(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(
            "sys.argv",
            ["import-schedule", str(tmp_path / "missing.pdf"), "--year", "2026", "--gym-id", "100"],
        )
        with pytest.raises(SystemExit) as exc:
            import_schedule.main()
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "not found" in err

    def test_no_schedules_exits_0(self, monkeypatch, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.touch()
        monkeypatch.setattr(
            "sys.argv",
            ["import-schedule", str(pdf), "--year", "2026", "--gym-id", "100"],
        )
        with patch.object(import_schedule, "extract_schedules_from_pdf", return_value=[]):
            with pytest.raises(SystemExit) as exc:
                import_schedule.main()
        assert exc.value.code == 0

    def test_dry_run_exits_0_without_db(self, monkeypatch, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.touch()
        monkeypatch.setattr(
            "sys.argv",
            [
                "import-schedule",
                str(pdf),
                "--year",
                "2026",
                "--gym-id",
                "100",
                "--dry-run",
            ],
        )
        with patch.object(
            import_schedule, "extract_schedules_from_pdf", return_value=[_schedule()]
        ):
            with pytest.raises(SystemExit) as exc:
                import_schedule.main()
        assert exc.value.code == 0

    def test_full_run_saves_to_db(self, monkeypatch, tmp_path):
        pdf = tmp_path / "x.pdf"
        pdf.touch()
        db = tmp_path / "test.db"
        monkeypatch.setattr(
            "sys.argv",
            [
                "import-schedule",
                str(pdf),
                "--year",
                "2026",
                "--gym-id",
                "100",
                "--db",
                str(db),
            ],
        )
        with patch.object(
            import_schedule, "extract_schedules_from_pdf", return_value=[_schedule()]
        ), patch.object(
            import_schedule, "resolve_exercise_interactive", return_value="Back Squat"
        ):
            import_schedule.main()
        # Verify DB has entry
        from wodplanner.services.schedule import ScheduleService

        svc = ScheduleService(db)
        rows = svc.get_by_date(date(2026, 4, 25))
        assert len(rows) == 1

    def test_metcon_long_preview_truncated(self, monkeypatch, tmp_path, capsys):
        pdf = tmp_path / "x.pdf"
        pdf.touch()
        long_metcon = "x" * 100
        long_sched = Schedule(
            date=date(2026, 4, 25),
            class_type="CrossFit",
            metcon=long_metcon,
        )
        monkeypatch.setattr(
            "sys.argv",
            [
                "import-schedule",
                str(pdf),
                "--year",
                "2026",
                "--gym-id",
                "100",
                "--dry-run",
            ],
        )
        with patch.object(
            import_schedule, "extract_schedules_from_pdf", return_value=[long_sched]
        ):
            with pytest.raises(SystemExit):
                import_schedule.main()
        out = capsys.readouterr().out
        assert "..." in out
