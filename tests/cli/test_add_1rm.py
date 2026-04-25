"""Tests for cli/add_1rm.py"""

import sys
from unittest.mock import patch

import pytest

from wodplanner.cli.add_1rm import main


class TestMain:
    def test_help_flag_exits(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, "argv", ["add-1rm", "--help"]):
                main()
        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "exercise" in out.lower()

    def test_add_exercise_success(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setenv("WODAPP_USERNAME", "test")
        monkeypatch.setenv("WODAPP_PASSWORD", "test")
        with patch.object(sys, "argv", ["add-1rm", "--exercise", "Deadlift"]):
            with patch("wodplanner.cli.add_1rm.OneRepMaxService") as MockSvc:
                MockSvc.return_value.get_exercise_list.return_value = ["Back Squat"]
                MockSvc.return_value.add_exercise.return_value = True
                with patch("wodplanner.cli.add_1rm.resolve_exercise_interactive", return_value="Deadlift"):
                    main()
        out = capsys.readouterr().out
        assert "Deadlift" in out

    def test_existing_exercise_exits(self, monkeypatch, capsys):
        monkeypatch.setenv("WODAPP_USERNAME", "test")
        monkeypatch.setenv("WODAPP_PASSWORD", "test")
        with patch.object(sys, "argv", ["add-1rm", "--exercise", "Back Squat"]):
            with patch("wodplanner.cli.add_1rm.OneRepMaxService") as MockSvc:
                MockSvc.return_value.get_exercise_list.return_value = ["Back Squat"]
                with patch("wodplanner.cli.add_1rm.resolve_exercise_interactive", return_value="Back Squat"):
                    with pytest.raises(SystemExit) as exc:
                        main()
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "already exists" in out

    def test_resolve_returns_none_exits(self, monkeypatch, capsys):
        monkeypatch.setenv("WODAPP_USERNAME", "test")
        monkeypatch.setenv("WODAPP_PASSWORD", "test")
        with patch.object(sys, "argv", ["add-1rm", "--exercise", "Unknown"]):
            with patch("wodplanner.cli.add_1rm.OneRepMaxService") as MockSvc:
                MockSvc.return_value.get_exercise_list.return_value = ["Back Squat"]
                with patch("wodplanner.cli.add_1rm.resolve_exercise_interactive", return_value=None):
                    with pytest.raises(SystemExit) as exc:
                        main()
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "Skipped" in out

    def test_empty_name_in_interactive_exits(self, monkeypatch, capsys):
        monkeypatch.setenv("WODAPP_USERNAME", "test")
        monkeypatch.setenv("WODAPP_PASSWORD", "test")
        with patch.object(sys, "argv", ["add-1rm"]):
            with patch("wodplanner.cli.add_1rm.OneRepMaxService") as MockSvc:
                MockSvc.return_value.get_exercise_list.return_value = ["Back Squat"]
                with patch("builtins.input", return_value=""):
                    with pytest.raises(SystemExit) as exc:
                        main()
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "No name provided" in out

    def test_interactive_mode_shows_exercises(self, monkeypatch, capsys):
        monkeypatch.setenv("WODAPP_USERNAME", "test")
        monkeypatch.setenv("WODAPP_PASSWORD", "test")
        with patch.object(sys, "argv", ["add-1rm"]):
            with patch("wodplanner.cli.add_1rm.OneRepMaxService") as MockSvc:
                MockSvc.return_value.get_exercise_list.return_value = ["Back Squat", "Clean"]
                with patch("builtins.input", side_effect=["Deadlift", ""]):
                    with patch("wodplanner.cli.add_1rm.resolve_exercise_interactive", return_value="Deadlift"):
                        MockSvc.return_value.add_exercise.return_value = True
                        main()
        out = capsys.readouterr().out
        assert "Existing exercises" in out
        assert "Back Squat" in out
