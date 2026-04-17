"""Schedule service for managing workout schedules."""

import sqlite3
from datetime import date, datetime
from pathlib import Path

from wodplanner.models.schedule import Schedule


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
    "HyCross 101": ["HyCross 101", "Hyrox 101"],
}


def normalize_class_name(class_name: str) -> str:
    """Normalize a class name to its canonical form."""
    # Strip whitespace and normalize
    normalized = class_name.strip()

    # Check direct mapping
    if normalized in CLASS_NAME_MAPPING:
        return CLASS_NAME_MAPPING[normalized][0]

    # Check if it's an alias
    for canonical, aliases in CLASS_NAME_MAPPING.items():
        if normalized in aliases:
            return canonical

    # Return as-is if no mapping found
    return normalized


def get_all_class_aliases(class_name: str) -> list[str]:
    """Get all possible aliases for a class name."""
    normalized = normalize_class_name(class_name)

    if normalized in CLASS_NAME_MAPPING:
        return CLASS_NAME_MAPPING[normalized]

    # Check if we need to search in aliases
    for canonical, aliases in CLASS_NAME_MAPPING.items():
        if class_name in aliases or normalized in aliases:
            return aliases

    return [class_name]


class ScheduleService:
    """Service for managing workout schedules with SQLite storage."""

    def __init__(self, db_path: str | Path = "wodplanner.db") -> None:
        self.db_path = Path(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE NOT NULL,
                    class_type TEXT NOT NULL,
                    warmup_mobility TEXT,
                    strength_specialty TEXT,
                    metcon TEXT,
                    raw_content TEXT,
                    source_file TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(date, class_type)
                )
            """)
            conn.commit()

    def _row_to_model(self, row: sqlite3.Row) -> Schedule:
        """Convert a database row to a Schedule model."""
        return Schedule(
            id=row["id"],
            date=date.fromisoformat(row["date"]),
            class_type=row["class_type"],
            warmup_mobility=row["warmup_mobility"],
            strength_specialty=row["strength_specialty"],
            metcon=row["metcon"],
            raw_content=row["raw_content"],
            source_file=row["source_file"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )

    def add(self, schedule: Schedule) -> Schedule:
        """Add a schedule entry (upsert - insert or update on conflict)."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO schedules
                (date, class_type, warmup_mobility, strength_specialty, metcon, raw_content, source_file, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date, class_type) DO UPDATE SET
                    warmup_mobility = excluded.warmup_mobility,
                    strength_specialty = excluded.strength_specialty,
                    metcon = excluded.metcon,
                    raw_content = excluded.raw_content,
                    source_file = excluded.source_file,
                    created_at = excluded.created_at
                """,
                (
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
            conn.commit()
            schedule.id = cursor.lastrowid
            schedule.created_at = datetime.now()
            return schedule

    def bulk_add(self, schedules: list[Schedule]) -> int:
        """Add multiple schedule entries. Returns count of entries added."""
        count = 0
        for schedule in schedules:
            self.add(schedule)
            count += 1
        return count

    def get_by_date_and_class(self, schedule_date: date, class_type: str) -> Schedule | None:
        """Get a schedule by date and class type, trying all aliases."""
        aliases = get_all_class_aliases(class_type)

        with self._get_connection() as conn:
            # Try each alias
            placeholders = ",".join("?" * len(aliases))
            row = conn.execute(
                f"SELECT * FROM schedules WHERE date = ? AND class_type IN ({placeholders})",
                (schedule_date.isoformat(), *aliases),
            ).fetchone()

            if row:
                return self._row_to_model(row)
            return None

    def get_by_date(self, schedule_date: date) -> list[Schedule]:
        """Get all schedules for a specific date."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM schedules WHERE date = ? ORDER BY class_type",
                (schedule_date.isoformat(),),
            ).fetchall()
            return [self._row_to_model(row) for row in rows]

    def find_for_appointment(self, appointment_name: str, appointment_date: date) -> Schedule | None:
        """Find a schedule that matches an appointment name and date."""
        return self.get_by_date_and_class(appointment_date, appointment_name)

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
