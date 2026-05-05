"""Benchmark WOD detection and service."""

import sqlite3
from datetime import datetime

from wodplanner.models.benchmark import BenchmarkWod
from wodplanner.services import migrations
from wodplanner.services.base import BaseService
from wodplanner.utils.dates import parse_iso_datetime

_SEED_BENCHMARKS: dict[str, list[str]] = {
    "The Girls": [
        "Fran", "Helen", "Cindy", "Annie", "Isabel", "Jackie", "Karen",
        "Angie", "Barbara", "Chelsea", "Diane", "Elizabeth", "Grace",
        "Linda", "Mary", "Nancy", "Amanda", "Eva",
    ],
    "Hero": [
        "Murph", "Kalsu", "JT", "Loredo", "Randy", "Danny", "Michael",
        "Nate", "Joshie", "Badger",
    ],
}


def find_benchmark_in_schedule(
    schedule_texts: list[str | None],
    benchmark_names: list[str],
) -> str | None:
    """Scan schedule text fields for known benchmark names (case-insensitive)."""
    combined = " ".join(t for t in schedule_texts if t)
    if not combined:
        return None
    lower_combined = combined.lower()
    for name in benchmark_names:
        if name.lower() in lower_combined:
            return name
    return None


def _migrate_v600(conn: sqlite3.Connection) -> None:
    """Create benchmark_wods table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS benchmark_wods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)


def _migrate_v601(conn: sqlite3.Connection) -> None:
    """Seed default benchmark WODs if empty."""
    if conn.execute("SELECT COUNT(*) FROM benchmark_wods").fetchone()[0] == 0:
        rows = [
            (name, category, datetime.now().isoformat())
            for category, names in _SEED_BENCHMARKS.items()
            for name in names
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO benchmark_wods (name, category, created_at) VALUES (?, ?, ?)",
            rows,
        )


migrations.register(600, "create benchmark_wods table", _migrate_v600)
migrations.register(601, "seed default benchmark WODs", _migrate_v601)


class BenchmarkService(BaseService):
    def _row_to_model(self, row: sqlite3.Row) -> BenchmarkWod:
        return BenchmarkWod(
            id=row["id"],
            name=row["name"],
            category=row["category"],
            created_at=parse_iso_datetime(row["created_at"]),
        )

    def get_benchmark_list(self) -> list[str]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT name FROM benchmark_wods ORDER BY name"
            ).fetchall()
            return [row["name"] for row in rows]

    def add_benchmark_wod(self, name: str, category: str) -> bool:
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO benchmark_wods (name, category, created_at) VALUES (?, ?, ?)",
                    (name.strip(), category.strip(), datetime.now().isoformat()),
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False
