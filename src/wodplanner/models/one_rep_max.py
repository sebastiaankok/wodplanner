"""One rep max models."""

from datetime import date, datetime

from pydantic import BaseModel


class OneRepMax(BaseModel):
    id: int | None = None
    user_id: int
    exercise: str
    weight_kg: float
    recorded_at: date
    notes: str | None = None
    created_at: datetime | None = None
