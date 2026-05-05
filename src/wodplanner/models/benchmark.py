"""Benchmark WOD models."""

from datetime import datetime

from pydantic import BaseModel


class BenchmarkWod(BaseModel):
    id: int | None = None
    name: str
    category: str
    created_at: datetime | None = None
