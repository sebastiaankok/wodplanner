"""Tests for cli/seed_subscriptions.py"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from wodplanner.cli.seed_subscriptions import generate_events, main


class TestGenerateEvents:
    def test_dry_run_does_not_insert(self, capsys):
        generate_events(
            user_id=42,
            weeks=2,
            avg_per_week=3,
            dry_run=True,
            db_path=Path("/tmp/nonexistent.db"),
        )
        out = capsys.readouterr().out
        assert "DRY RUN" in out
        assert "Total:" in out

    def test_zero_weeks(self, capsys):
        generate_events(
            user_id=42,
            weeks=0,
            avg_per_week=3,
            dry_run=True,
            db_path=Path("/tmp/nonexistent.db"),
        )
        out = capsys.readouterr().out
        assert "Total: 0 events" in out

    def test_insert_with_mock_service(self, capsys, tmp_path):
        db_path = tmp_path / "test.db"
        with patch("wodplanner.cli.seed_subscriptions.SubscriptionTrackerService") as MockSvc:
            mock_instance = MockSvc.return_value
            generate_events(
                user_id=42,
                weeks=1,
                avg_per_week=1,
                dry_run=False,
                db_path=db_path,
            )
            assert mock_instance.record_subscribe.call_count >= 1
        out = capsys.readouterr().out
        assert "events inserted" in out


class TestMain:
    def test_help_flag_exits(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, "argv", ["seed-subscriptions", "--help"]):
                main()
        assert exc_info.value.code == 0

    def test_dry_run(self, capsys):
        with patch.object(sys, "argv", ["seed-subscriptions", "--user-id", "1", "--weeks", "1", "--dry-run"]):
            main()
        out = capsys.readouterr().out
        assert "DRY RUN" in out

    def test_custom_args(self, capsys, tmp_path):
        db_path = tmp_path / "test.db"
        with patch.object(sys, "argv", [
            "seed-subscriptions",
            "--user-id", "99",
            "--weeks", "2",
            "--avg-per-week", "1",
            "--db-path", str(db_path),
        ]):
            with patch("wodplanner.cli.seed_subscriptions.SubscriptionTrackerService"):
                main()
        out = capsys.readouterr().out
        assert "user 99" in out

    def test_missing_user_id_exits(self, capsys):
        with pytest.raises(SystemExit):
            with patch.object(sys, "argv", ["seed-subscriptions"]):
                main()