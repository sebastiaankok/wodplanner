"""Tests for cli/add_benchmark.py"""

import sys
from unittest.mock import patch

import pytest

from wodplanner.cli.add_benchmark import main


class TestMain:
    def test_help_flag_exits(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, "argv", ["add-benchmark", "--help"]):
                main()
        assert exc_info.value.code == 0

    def test_add_benchmark_success(self, monkeypatch, capsys):
        with patch.object(sys, "argv", ["add-benchmark", "--name", "Fran"]):
            with patch("wodplanner.cli.add_benchmark.BenchmarkService") as MockSvc:
                MockSvc.return_value.add_benchmark_wod.return_value = True
                MockSvc.return_value.get_benchmark_list.return_value = []
                with patch("builtins.input", return_value="Benchmark"):
                    main()
        out = capsys.readouterr().out
        assert "Fran" in out
        assert "added" in out.lower()

    def test_existing_benchmark_exits(self, capsys):
        with patch.object(sys, "argv", ["add-benchmark", "--name", "Fran"]):
            with patch("wodplanner.cli.add_benchmark.BenchmarkService") as MockSvc:
                MockSvc.return_value.add_benchmark_wod.return_value = False
                MockSvc.return_value.get_benchmark_list.return_value = ["Fran"]
                with patch("builtins.input", return_value="Benchmark"):
                    with pytest.raises(SystemExit) as exc:
                        main()
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "already exists" in out

    def test_interactive_mode(self, capsys):
        with patch.object(sys, "argv", ["add-benchmark"]):
            with patch("wodplanner.cli.add_benchmark.BenchmarkService") as MockSvc:
                MockSvc.return_value.get_benchmark_list.return_value = ["Fran", "Helen"]
                MockSvc.return_value.add_benchmark_wod.return_value = True
                with patch("builtins.input", side_effect=["Nasty Girls", "Benchmark"]):
                    main()
        out = capsys.readouterr().out
        assert "Existing benchmark WODs" in out
        assert "Fran" in out
        assert "Helen" in out

    def test_interactive_empty_name_exits(self, capsys):
        with patch.object(sys, "argv", ["add-benchmark"]):
            with patch("wodplanner.cli.add_benchmark.BenchmarkService") as MockSvc:
                MockSvc.return_value.get_benchmark_list.return_value = []
                with patch("builtins.input", return_value=""):
                    with pytest.raises(SystemExit) as exc:
                        main()
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "No name provided" in out

    def test_custom_category(self, monkeypatch, capsys):
        with patch.object(sys, "argv", ["add-benchmark", "--name", "Murph", "--category", "Hero"]):
            with patch("wodplanner.cli.add_benchmark.BenchmarkService") as MockSvc:
                MockSvc.return_value.add_benchmark_wod.return_value = True
                MockSvc.return_value.get_benchmark_list.return_value = []
                with patch("builtins.input", return_value=""):
                    main()
        out = capsys.readouterr().out
        assert "Murph" in out
        assert "Hero" in out

    def test_custom_db_path(self, tmp_path):
        db_file = tmp_path / "custom.db"
        with patch.object(sys, "argv", ["add-benchmark", "--name", "Cindy", "--db", str(db_file)]):
            with patch("wodplanner.cli.add_benchmark.BenchmarkService") as MockSvc:
                MockSvc.return_value.add_benchmark_wod.return_value = True
                MockSvc.return_value.get_benchmark_list.return_value = []
                with patch("builtins.input", return_value="Benchmark"):
                    main()