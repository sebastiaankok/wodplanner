"""Benchmark WOD detection and service."""

import sqlite3
from datetime import datetime

from wodplanner.models.benchmark import BenchmarkResult, BenchmarkWod
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


def _migrate_v602(conn: sqlite3.Connection) -> None:
    """Create benchmark_results table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS benchmark_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            benchmark_name TEXT NOT NULL,
            time_seconds INTEGER NOT NULL,
            is_rx INTEGER NOT NULL DEFAULT 1,
            recorded_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)


migrations.register(600, "create benchmark_wods table", _migrate_v600)
migrations.register(601, "seed default benchmark WODs", _migrate_v601)
migrations.register(602, "create benchmark_results table", _migrate_v602)


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

    def _row_to_result(self, row: sqlite3.Row) -> BenchmarkResult:
        return BenchmarkResult(
            id=row["id"],
            user_id=row["user_id"],
            benchmark_name=row["benchmark_name"],
            time_seconds=row["time_seconds"],
            is_rx=bool(row["is_rx"]),
            recorded_at=row["recorded_at"],
            created_at=parse_iso_datetime(row["created_at"]),
        )

    def add_result(
        self, user_id: int, benchmark_name: str, time_seconds: int, is_rx: bool, recorded_at: str
    ) -> BenchmarkResult:
        with self._get_connection() as conn:
            row = conn.execute(
                "INSERT INTO benchmark_results (user_id, benchmark_name, time_seconds, is_rx, recorded_at, created_at) VALUES (?, ?, ?, ?, ?, ?) RETURNING *",
                (user_id, benchmark_name.strip(), time_seconds, int(is_rx), recorded_at, datetime.now().isoformat()),
            ).fetchone()
            conn.commit()
            return self._row_to_result(row)

    def get_results_for_benchmark(self, user_id: int, benchmark_name: str) -> list[BenchmarkResult]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM benchmark_results WHERE user_id = ? AND benchmark_name = ? ORDER BY recorded_at DESC",
                (user_id, benchmark_name),
            ).fetchall()
            return [self._row_to_result(row) for row in rows]

    def get_result(self, user_id: int, result_id: int) -> BenchmarkResult | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM benchmark_results WHERE id = ? AND user_id = ?",
                (result_id, user_id),
            ).fetchone()
            return self._row_to_result(row) if row else None

    def delete_result(self, user_id: int, result_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM benchmark_results WHERE id = ? AND user_id = ?",
                (result_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0
