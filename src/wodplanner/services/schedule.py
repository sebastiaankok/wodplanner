"""Schedule service for managing workout schedules."""

import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

from wodplanner.models.schedule import Schedule
from wodplanner.services.db import get_connection


# Mapping from PDF class names to possible API names
CLASS_NAME_MAPPING: dict[str, list[str]] = {
    "CrossFit": ["CrossFit"],
    "CrossFit 101": ["CrossFit 101", "CF101"],
    "CF101": ["CrossFit 101", "CF101"],
    "Boxing Class": ["Boxing Class", "Boxing"],
    "HyCross": ["HyCross", "Hyrox"],
    "Gymnastics": ["Gymnastics"],
    "Olympic Lifting": ["Olympic Lifting", "Oly"],
    "Oly": ["Olympic Lifting", "Oly"],
    "Olympic Lifting 101": ["Olympic Lifting 101", "Oly101"],
    "Oly101": ["Olympic Lifting 101", "Oly101"],
    "Strength Class": ["Strength Class", "Strength"],
    "Teen Athlete": ["Teen Athlete"],
    "CrossFit & Teen Athlete": ["CrossFit", "Teen Athlete"],
    "Strongman": ["Strongman"],
    "Strongman101": ["Strongman101", "Strongman 101"],
    "Gymnastics 101": ["Gymnastics 101"],
    "HyCross 101": ["HyCross 101", "Hyrox 101", "HyCross101"],
}


def normalize_class_name(class_name: str) -> str:
    """Normalize a class name to its canonical form."""
    normalized = re.sub(r'\s+', ' ', class_name).strip()

    if normalized in CLASS_NAME_MAPPING:
        return CLASS_NAME_MAPPING[normalized][0]

    for canonical, aliases in CLASS_NAME_MAPPING.items():
        if normalized in aliases:
            return canonical

    return normalized


def get_all_class_aliases(class_name: str) -> list[str]:
    """Get all DB class_type values that could match this API class name."""
    normalized = normalize_class_name(class_name)
    results: set[str] = set()

    if normalized in CLASS_NAME_MAPPING:
        results.update(CLASS_NAME_MAPPING[normalized])

    # Reverse lookup: canonical names where this class appears as an alias
    for canonical, aliases in CLASS_NAME_MAPPING.items():
        if class_name in aliases or normalized in aliases:
            results.add(canonical)

    return list(results) if results else [class_name]


class ScheduleService:
    """Service for managing workout schedules with SQLite storage."""

    def __init__(self, db_path: str | Path = "wodplanner.db") -> None:
        self.db_path = Path(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return get_connection(self.db_path)

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    gym_id INTEGER,
                    date DATE NOT NULL,
                    class_type TEXT NOT NULL,
                    warmup_mobility TEXT,
                    strength_specialty TEXT,
                    metcon TEXT,
                    raw_content TEXT,
                    source_file TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(date, class_type, gym_id)
                )
            """)
            conn.commit()
            self._migrate_db(conn)

    def _migrate_db(self, conn: sqlite3.Connection) -> None:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(schedules)")]
        if "gym_id" not in cols:
            conn.execute("""
                CREATE TABLE schedules_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    gym_id INTEGER,
                    date DATE NOT NULL,
                    class_type TEXT NOT NULL,
                    warmup_mobility TEXT,
                    strength_specialty TEXT,
                    metcon TEXT,
                    raw_content TEXT,
                    source_file TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(date, class_type, gym_id)
                )
            """)
            conn.execute("""
                INSERT INTO schedules_new
                SELECT id, NULL, date, class_type, warmup_mobility,
                       strength_specialty, metcon, raw_content, source_file, created_at
                FROM schedules
            """)
            conn.execute("DROP TABLE schedules")
            conn.execute("ALTER TABLE schedules_new RENAME TO schedules")
            conn.commit()

    def _row_to_model(self, row: sqlite3.Row) -> Schedule:
        """Convert a database row to a Schedule model."""
        return Schedule(
            id=row["id"],
            gym_id=row["gym_id"],
            date=date.fromisoformat(row["date"]),
            class_type=row["class_type"],
            warmup_mobility=row["warmup_mobility"],
            strength_specialty=row["strength_specialty"],
            metcon=row["metcon"],
            raw_content=row["raw_content"],
            source_file=row["source_file"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )

    def _execute_add(self, conn: sqlite3.Connection, schedule: Schedule) -> int | None:
        cursor = conn.execute(
            """
            INSERT INTO schedules
            (gym_id, date, class_type, warmup_mobility, strength_specialty, metcon, raw_content, source_file, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, class_type, gym_id) DO UPDATE SET
                warmup_mobility = excluded.warmup_mobility,
                strength_specialty = excluded.strength_specialty,
                metcon = excluded.metcon,
                raw_content = excluded.raw_content,
                source_file = excluded.source_file,
                created_at = excluded.created_at
            """,
            (
                schedule.gym_id,
                schedule.date.isoformat(),
                schedule.class_type,
                schedule.warmup_mobility,
                schedule.strength_specialty,
                schedule.metcon,
                schedule.raw_content,
                schedule.source_file,
                datetime.now().isoformat(),
            ),
        )
        return cursor.lastrowid

    def add(self, schedule: Schedule) -> Schedule:
        """Add a schedule entry (upsert - insert or update on conflict)."""
        with self._get_connection() as conn:
            schedule.id = self._execute_add(conn, schedule)
            conn.commit()
        schedule.created_at = datetime.now()
        return schedule

    def bulk_add(self, schedules: list[Schedule]) -> int:
        """Add multiple schedule entries in a single transaction. Returns count of entries added."""
        with self._get_connection() as conn:
            for schedule in schedules:
                schedule.id = self._execute_add(conn, schedule)
            conn.commit()
        return len(schedules)

    def get_by_date_and_class(self, schedule_date: date, class_type: str, gym_id: int | None = None) -> Schedule | None:
        """Get a schedule by date and class type, trying all aliases."""
        aliases = get_all_class_aliases(class_type)

        with self._get_connection() as conn:
            placeholders = ",".join("?" * len(aliases))
            if gym_id is not None:
                row = conn.execute(
                    f"SELECT * FROM schedules WHERE date = ? AND class_type IN ({placeholders}) AND (gym_id = ? OR gym_id IS NULL)",
                    (schedule_date.isoformat(), *aliases, gym_id),
                ).fetchone()
            else:
                row = conn.execute(
                    f"SELECT * FROM schedules WHERE date = ? AND class_type IN ({placeholders})",
                    (schedule_date.isoformat(), *aliases),
                ).fetchone()

            if row:
                return self._row_to_model(row)
            return None

    def get_by_date(self, schedule_date: date, gym_id: int | None = None) -> list[Schedule]:
        """Get all schedules for a specific date."""
        with self._get_connection() as conn:
            if gym_id is not None:
                rows = conn.execute(
                    "SELECT * FROM schedules WHERE date = ? AND (gym_id = ? OR gym_id IS NULL) ORDER BY class_type",
                    (schedule_date.isoformat(), gym_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM schedules WHERE date = ? ORDER BY class_type",
                    (schedule_date.isoformat(),),
                ).fetchall()
            return [self._row_to_model(row) for row in rows]

    def find_for_appointment(self, appointment_name: str, appointment_date: date, gym_id: int | None = None) -> Schedule | None:
        """Find a schedule that matches an appointment name and date."""
        return self.get_by_date_and_class(appointment_date, appointment_name, gym_id=gym_id)

    def get_all(self) -> list[Schedule]:
        """Get all schedules."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM schedules ORDER BY date, class_type"
            ).fetchall()
            return [self._row_to_model(row) for row in rows]

    def delete_by_date(self, schedule_date: date) -> int:
        """Delete all schedules for a date. Returns count of deleted entries."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM schedules WHERE date = ?",
                (schedule_date.isoformat(),),
            )
            conn.commit()
            return cursor.rowcount
