"""Tests for models/one_rep_max.py"""

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from wodplanner.models.one_rep_max import OneRepMax


class TestOneRepMax:
    def test_required_fields(self):
        orm = OneRepMax(user_id=1, exercise="Back Squat", weight_kg=100.0, recorded_at=date(2026, 1, 1))
        assert orm.user_id == 1
        assert orm.exercise == "Back Squat"
        assert orm.weight_kg == 100.0
        assert orm.recorded_at == date(2026, 1, 1)

    def test_optional_fields_default(self):
        orm = OneRepMax(user_id=1, exercise="Back Squat", weight_kg=100.0, recorded_at=date(2026, 1, 1))
        assert orm.id is None
        assert orm.notes is None
        assert orm.created_at is None

    def test_all_fields(self):
        now = datetime(2026, 1, 1, 12, 0)
        orm = OneRepMax(
            id=1,
            user_id=1,
            exercise="Back Squat",
            weight_kg=100.0,
            recorded_at=date(2026, 1, 1),
            notes="Test note",
            created_at=now,
        )
        assert orm.id == 1
        assert orm.notes == "Test note"
        assert orm.created_at == now

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            OneRepMax(user_id=1, exercise="Back Squat", weight_kg=100.0)  # missing recorded_at

    def test_missing_required_field_raises_exercise(self):
        with pytest.raises(ValidationError):
            OneRepMax(user_id=1, weight_kg=100.0, recorded_at=date(2026, 1, 1))  # missing exercise
