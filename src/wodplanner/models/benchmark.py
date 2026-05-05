"""Benchmark WOD models."""

from datetime import datetime

from pydantic import BaseModel


class BenchmarkWod(BaseModel):
    id: int | None = None
    name: str
    category: str
    created_at: datetime | None = None


class BenchmarkResult(BaseModel):
    id: int | None = None
    user_id: int
    benchmark_name: str
    time_seconds: int
    is_rx: bool = True
    recorded_at: str
    created_at: datetime | None = None
