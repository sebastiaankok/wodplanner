"""Schedule models for workout schedule import."""

from datetime import date, datetime

from pydantic import BaseModel


class Schedule(BaseModel):
    """A workout schedule entry imported from PDF."""

    id: int | None = None
    date: date
    class_type: str
    warmup_mobility: str | None = None
    strength_specialty: str | None = None
    metcon: str | None = None
    raw_content: str | None = None
    source_file: str | None = None
    created_at: datetime | None = None


class ScheduleResponse(BaseModel):
    """API response model for schedule."""

    date: date
    class_type: str
    warmup_mobility: str | None = None
    strength_specialty: str | None = None
    metcon: str | None = None
