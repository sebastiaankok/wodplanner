"""Tests for models/schedule.py"""

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from wodplanner.models.schedule import Schedule, ScheduleResponse


class TestSchedule:
    def test_required_fields(self):
        sched = Schedule(date=date(2026, 1, 1), class_type="CrossFit")
        assert sched.date == date(2026, 1, 1)
        assert sched.class_type == "CrossFit"

    def test_optional_fields_default(self):
        sched = Schedule(date=date(2026, 1, 1), class_type="CrossFit")
        assert sched.id is None
        assert sched.gym_id is None
        assert sched.warmup_mobility is None
        assert sched.strength_specialty is None
        assert sched.metcon is None
        assert sched.raw_content is None
        assert sched.source_file is None
        assert sched.created_at is None

    def test_all_fields(self):
        now = datetime(2026, 1, 1, 12, 0)
        sched = Schedule(
            id=1,
            gym_id=2,
            date=date(2026, 1, 1),
            class_type="CrossFit",
            warmup_mobility="Warmup",
            strength_specialty="Strength",
            metcon="21-15-9",
            raw_content="Raw",
            source_file="file.pdf",
            created_at=now,
        )
        assert sched.id == 1
        assert sched.gym_id == 2
        assert sched.warmup_mobility == "Warmup"
        assert sched.strength_specialty == "Strength"
        assert sched.metcon == "21-15-9"

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            Schedule(class_type="CrossFit")  # missing date


class TestScheduleResponse:
    def test_required_fields(self):
        resp = ScheduleResponse(date=date(2026, 1, 1), class_type="CrossFit")
        assert resp.date == date(2026, 1, 1)
        assert resp.class_type == "CrossFit"

    def test_optional_fields_default(self):
        resp = ScheduleResponse(date=date(2026, 1, 1), class_type="CrossFit")
        assert resp.warmup_mobility is None
        assert resp.strength_specialty is None
        assert resp.metcon is None

    def test_all_fields(self):
        resp = ScheduleResponse(
            date=date(2026, 1, 1),
            class_type="CrossFit",
            warmup_mobility="Warmup",
            strength_specialty="Strength",
            metcon="21-15-9",
        )
        assert resp.warmup_mobility == "Warmup"
        assert resp.strength_specialty == "Strength"
        assert resp.metcon == "21-15-9"

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            ScheduleResponse(class_type="CrossFit")  # missing date
