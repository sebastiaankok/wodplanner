from unittest.mock import patch

from wodplanner.services.one_rep_max import (
    OneRepMaxService,
    extract_1rm_exercises,
    has_1rm_exercise,
    resolve_exercise_interactive,
)


class TestHas1rmExercise:
    def test_no_text_returns_false(self):
        assert has_1rm_exercise(None) is False
        assert has_1rm_exercise("") is False

    def test_1rm_as_percentage_not_counted(self):
        assert has_1rm_exercise("80% 1RM") is False
        assert has_1rm_exercise("90%  1rm") is False

    def test_1rm_as_exercise_counted(self):
        assert has_1rm_exercise("1RM Back Squat") is True
        assert has_1rm_exercise("test 1rm workout") is True
        assert has_1rm_exercise("1RM") is True

    def test_1rm_case_insensitive(self):
        assert has_1rm_exercise("1RM Test") is True
        assert has_1rm_exercise("1rm Test") is True
        assert has_1rm_exercise("TEST 1RM") is True


class TestExtract1rmExercises:
    def test_no_text_returns_empty(self):
        assert extract_1rm_exercises(None) == []
        assert extract_1rm_exercises("") == []

    def test_extracts_exercise_name(self):
        text = "1RM Back Squat"
        result = extract_1rm_exercises(text)
        assert "Back Squat" in result

    def test_ignores_percentage_references(self):
        text = "80% 1RM Back Squat"
        result = extract_1rm_exercises(text)
        assert len(result) == 0

    def test_extracts_multiple_exercises(self):
        text = "A. 1RM Back Squat B. 1RM Clean"
        result = extract_1rm_exercises(text)
        assert len(result) == 2

    def test_strips_parenthetical_annotations(self):
        text = "1RM Back Squat (test note)"
        result = extract_1rm_exercises(text)
        assert "(" not in result[0]
        assert "Back Squat" in result[0]

    def test_handles_multiline(self):
        text = "A. 1RM Snatch B. 1RM Clean"
        result = extract_1rm_exercises(text)
        assert len(result) == 2


class TestResolveExerciseInteractive:
    def test_exact_match_returns_silently(self, monkeypatch):
        exercises = ["Back Squat", "Clean", "Snatch"]
        with patch("builtins.input", return_value=""):
            result = resolve_exercise_interactive("Back Squat", exercises)
        assert result == "Back Squat"

    def test_no_match_offers_add_as_new(self, monkeypatch):
        exercises = ["Back Squat", "Clean"]
        with patch("builtins.input", return_value="1"):
            result = resolve_exercise_interactive("Deadlift", exercises)
        assert result == "Deadlift"

    def test_no_match_skip_returns_none(self, monkeypatch):
        exercises = ["Back Squat", "Clean"]
        with patch("builtins.input", return_value="3"):
            result = resolve_exercise_interactive("Deadlift", exercises)
        assert result is None

    def test_fuzzy_match_accept_match(self, monkeypatch):
        exercises = ["Back Squat", "Clean"]
        with patch("builtins.input", return_value="1"):
            result = resolve_exercise_interactive("Back Sqaut", exercises)
        assert result == "Back Squat"

    def test_fuzzy_match_add_as_new(self, monkeypatch):
        exercises = ["Back Squat", "Clean"]
        with patch("builtins.input", return_value="2"):
            result = resolve_exercise_interactive("Back Sqaut", exercises)
        assert result == "Back Sqaut"

    def test_fuzzy_match_rename(self, monkeypatch):
        exercises = ["Back Squat", "Clean"]
        calls = iter(["3", "New Exercise", "1"])
        monkeypatch.setattr("builtins.input", lambda _: next(calls))
        result = resolve_exercise_interactive("Back Sqaut", exercises)
        assert result == "New Exercise"

    def test_fuzzy_match_skip_returns_none(self, monkeypatch):
        exercises = ["Back Squat", "Clean"]
        with patch("builtins.input", return_value="4"):
            result = resolve_exercise_interactive("Back Sqaut", exercises)
        assert result is None


class TestOneRepMaxService:
    def test_get_exercise_list(self, db_path):
        svc = OneRepMaxService(db_path)
        exercises = svc.get_exercise_list()
        assert len(exercises) > 0
        assert "Back Squat" in exercises

    def test_add_exercise(self, db_path):
        svc = OneRepMaxService(db_path)
        result = svc.add_exercise("New Exercise")
        assert result is True

        exercises = svc.get_exercise_list()
        assert "New Exercise" in exercises

    def test_add_exercise_duplicate_returns_false(self, db_path):
        svc = OneRepMaxService(db_path)
        svc.add_exercise("Duplicate Test")
        result = svc.add_exercise("Duplicate Test")
        assert result is False

    def test_validate_exercise(self, db_path):
        svc = OneRepMaxService(db_path)
        assert svc.validate_exercise("Back Squat") is True
        assert svc.validate_exercise("Nonexistent Exercise") is False

    def test_match_exercise(self, db_path):
        svc = OneRepMaxService(db_path)
        result = svc.match_exercise("Back Sqaut")
        assert result == "Back Squat"

    def test_match_exercise_no_match(self, db_path):
        svc = OneRepMaxService(db_path)
        result = svc.match_exercise("xyznonexistent")
        assert result is None

    def test_add_and_get_1rm(self, db_path):
        from datetime import date

        svc = OneRepMaxService(db_path)
        entry = svc.add(user_id=1, exercise="Back Squat", weight_kg=100.0, recorded_at=date(2026, 1, 1))
        assert entry.id is not None
        assert entry.weight_kg == 100.0

        results = svc.get_all(user_id=1)
        assert len(results) == 1

    def test_get_for_exercise(self, db_path):
        from datetime import date

        svc = OneRepMaxService(db_path)
        svc.add(user_id=1, exercise="Back Squat", weight_kg=100.0, recorded_at=date(2026, 1, 1))
        svc.add(user_id=1, exercise="Back Squat", weight_kg=105.0, recorded_at=date(2026, 2, 1))
        svc.add(user_id=1, exercise="Clean", weight_kg=80.0, recorded_at=date(2026, 1, 1))

        results = svc.get_for_exercise(user_id=1, exercise="Back Squat")
        assert len(results) == 2

    def test_get_max_for_exercise(self, db_path):
        from datetime import date

        svc = OneRepMaxService(db_path)
        svc.add(user_id=1, exercise="Back Squat", weight_kg=100.0, recorded_at=date(2026, 1, 1))
        svc.add(user_id=1, exercise="Back Squat", weight_kg=105.0, recorded_at=date(2026, 2, 1))

        max_weight = svc.get_max_for_exercise(user_id=1, exercise="Back Squat")
        assert max_weight == 105.0

    def test_get_max_for_exercise_none(self, db_path):
        svc = OneRepMaxService(db_path)
        max_weight = svc.get_max_for_exercise(user_id=1, exercise="Nonexistent")
        assert max_weight is None

    def test_delete(self, db_path):
        from datetime import date

        svc = OneRepMaxService(db_path)
        entry = svc.add(user_id=1, exercise="Back Squat", weight_kg=100.0, recorded_at=date(2026, 1, 1))
        deleted = svc.delete(user_id=1, entry_id=entry.id)
        assert deleted is True

        results = svc.get_all(user_id=1)
        assert len(results) == 0

    def test_delete_wrong_user_returns_false(self, db_path):
        from datetime import date

        svc = OneRepMaxService(db_path)
        entry = svc.add(user_id=1, exercise="Back Squat", weight_kg=100.0, recorded_at=date(2026, 1, 1))
        deleted = svc.delete(user_id=999, entry_id=entry.id)
        assert deleted is False