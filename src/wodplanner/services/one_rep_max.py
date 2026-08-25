"""One rep max service."""

import difflib
import re
import sqlite3
from datetime import date, datetime

from wodplanner.models.one_rep_max import OneRepMax
from wodplanner.services import migrations
from wodplanner.services.base import BaseService
from wodplanner.utils.dates import parse_iso_date, parse_iso_datetime

_SEED_EXERCISES: list[str] = [
    "Snatch",
    "Clean",
    "Clean & Jerk",
    "Power Snatch",
    "Power Clean",
    "Split Jerk",
    "Push Jerk",
    "Back Squat",
    "Box Back Squat",
    "Box Front Squat",
    "Front Squat",
    "Overhead Squat",
    "Deadlift",
    "Sumo Deadlift",
    "Strict Press",
    "Push Press",
    "Bench Press",
    "Floor Press",
    "Weighted Pull-Up",
    "Weighted Chin-Up",
    "Thruster",
    "Hang Clean",
    "Hang Power Clean",
    "Hang Snatch",
    "Weighted Dip",
    "Weighted Ring Dip",
    "Weighted Strict Muscle-Up",
    "Weighted Ring Muscle-Up",
]


def resolve_exercise_interactive(raw_name: str, exercises: list[str]) -> str | None:
    """Prompt operator to map raw_name to an existing exercise or accept as new.

    Exact match: returns silently.
    Fuzzy match: asks to accept or skip.
    No match: suggests adding as new, asks to accept or skip.
    Returns: a name from exercises (existing), a new name not in exercises, or None (skip).
    Caller is responsible for persisting a new name to the DB.
    """
    if raw_name in exercises:
        return raw_name
    matches = difflib.get_close_matches(raw_name, exercises, n=1, cutoff=0.6)
    if matches:
        print(f'  "{raw_name}" → closest match: "{matches[0]}"')
        ans = input("  [1] Accept match  [2] Add as new  [3] Rename  [4] Skip: ").strip()
        if ans == "1":
            return matches[0]
        if ans == "2":
            return raw_name
        if ans == "3":
            new_name = input("  New name: ").strip()
            return resolve_exercise_interactive(new_name, exercises) if new_name else None
        return None
    else:
        print(f'  No match for "{raw_name}".')
        ans = input("  [1] Add as new  [2] Rename  [3] Skip: ").strip()
        if ans == "1":
            return raw_name
        if ans == "2":
            new_name = input("  New name: ").strip()
            return resolve_exercise_interactive(new_name, exercises) if new_name else None
        return None


def has_1rm_exercise(text: str | None) -> bool:
    """True if text contains '1rm' as an exercise, not a percentage reference."""
    if not text:
        return False
    for m in re.finditer(r'1rm', text, re.IGNORECASE):
        preceding = text[max(0, m.start() - 6):m.start()]
        if not re.search(r'\d+%\s*$', preceding):
            return True
    return False


def extract_1rm_exercises(text: str | None) -> list[str]:
    """Extract exercise names following '1rm' (non-percentage occurrences)."""
    if not text:
        return []
    results = []
    # Capture everything up to the next exercise letter (e.g. "B.") or end of string
    for m in re.finditer(r'1rm\s+(.+?)(?=\s+[A-Z]\.\s|\n(?!\s*[A-Za-z])|\s*\Z)', text, re.IGNORECASE | re.DOTALL):
        preceding = text[max(0, m.start() - 6):m.start()]
        if not re.search(r'\d+%\s*$', preceding):
            # Strip parenthetical annotations, collapse internal whitespace/newlines
            name = re.sub(r'\s*\([^)]*\)', '', m.group(1))
            name = re.sub(r'\s+', ' ', name).strip()
            if name:
                results.append(name)
    return results


def _migrate_v400(conn: sqlite3.Connection) -> None:
    """Create exercises and one_rep_maxes tables."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS one_rep_maxes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            exercise TEXT NOT NULL,
            weight_kg REAL NOT NULL,
            recorded_at TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL
        )
        """
    )


def _migrate_v401(conn: sqlite3.Connection) -> None:
    """Seed default exercise list if empty."""
    if conn.execute("SELECT COUNT(*) FROM exercises").fetchone()[0] == 0:
        conn.executemany(
            "INSERT OR IGNORE INTO exercises (name, created_at) VALUES (?, ?)",
            [(name, datetime.now().isoformat()) for name in _SEED_EXERCISES],
        )


migrations.register(400, "create exercises and one_rep_maxes tables", _migrate_v400)
migrations.register(401, "seed default exercises", _migrate_v401)


def _migrate_v804(conn: sqlite3.Connection) -> None:
    """Recreate one_rep_maxes with FK to users/exercises, CHECK, soft-delete, indexes."""
    if migrations.has_fk_to(conn, "one_rep_maxes", "users") and migrations.has_column(
        conn, "one_rep_maxes", "updated_at"
    ):
        return
    with migrations.fk_disabled(conn):
        conn.execute("ALTER TABLE one_rep_maxes RENAME TO one_rep_maxes_old")
        conn.execute(
            """
            CREATE TABLE one_rep_maxes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                exercise TEXT NOT NULL REFERENCES exercises(name) ON UPDATE CASCADE ON DELETE RESTRICT,
                weight_kg REAL NOT NULL CHECK(weight_kg > 0),
                recorded_at TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO one_rep_maxes
                (id, user_id, exercise, weight_kg, recorded_at, notes, created_at, updated_at, deleted_at)
            SELECT id, user_id, exercise, weight_kg, recorded_at, notes, created_at, created_at, NULL
            FROM one_rep_maxes_old
            """
        )
        conn.execute("DROP TABLE one_rep_maxes_old")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orm_user_exercise ON one_rep_maxes(user_id, exercise)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orm_user_recorded ON one_rep_maxes(user_id, recorded_at)")


migrations.register(804, "recreate one_rep_maxes with FK + soft-delete", _migrate_v804)


def _migrate_v808(conn: sqlite3.Connection) -> None:
    """Add deleted_at + updated_at to exercises."""
    if not migrations.has_column(conn, "exercises", "deleted_at"):
        conn.execute("ALTER TABLE exercises ADD COLUMN deleted_at TEXT")
    if not migrations.has_column(conn, "exercises", "updated_at"):
        conn.execute("ALTER TABLE exercises ADD COLUMN updated_at TEXT")


migrations.register(808, "add soft-delete + updated_at to exercises", _migrate_v808)


class OneRepMaxService(BaseService):
    def _row_to_model(self, row: sqlite3.Row) -> OneRepMax:
        return OneRepMax(
            id=row["id"],
            user_id=row["user_id"],
            exercise=row["exercise"],
            weight_kg=row["weight_kg"],
            recorded_at=parse_iso_date(row["recorded_at"]),
            notes=row["notes"],
            created_at=parse_iso_datetime(row["created_at"]),
        )

    def add(self, user_id: int, exercise: str, weight_kg: float, recorded_at: date, notes: str | None = None) -> OneRepMax:
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            row = conn.execute(
                "INSERT INTO one_rep_maxes (user_id, exercise, weight_kg, recorded_at, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING *",
                (user_id, exercise.strip(), weight_kg, recorded_at.isoformat(), notes, now, now),
            ).fetchone()
            conn.commit()
            return self._row_to_model(row)

    def get_all(self, user_id: int) -> list[OneRepMax]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM one_rep_maxes WHERE user_id = ? AND deleted_at IS NULL ORDER BY recorded_at DESC, created_at DESC",
                (user_id,),
            ).fetchall()
            return [self._row_to_model(row) for row in rows]

    def get_for_exercise(self, user_id: int, exercise: str) -> list[OneRepMax]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM one_rep_maxes WHERE user_id = ? AND exercise = ? AND deleted_at IS NULL ORDER BY recorded_at DESC",
                (user_id, exercise),
            ).fetchall()
            return [self._row_to_model(row) for row in rows]

    def get_exercises(self, user_id: int) -> list[str]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT exercise FROM one_rep_maxes WHERE user_id = ? AND deleted_at IS NULL ORDER BY exercise",
                (user_id,),
            ).fetchall()
            return [row["exercise"] for row in rows]

    def delete(self, user_id: int, entry_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE one_rep_maxes SET deleted_at = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                (datetime.now().isoformat(), entry_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_exercise_list(self) -> list[str]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT name FROM exercises WHERE deleted_at IS NULL ORDER BY name"
            ).fetchall()
            return [row["name"] for row in rows]

    def add_exercise(self, name: str) -> bool:
        """Add exercise to list. Returns False if already exists."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO exercises (name, created_at, updated_at) VALUES (?, ?, ?)",
                    (name.strip(), datetime.now().isoformat(), datetime.now().isoformat()),
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False

    def validate_exercise(self, name: str) -> bool:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM exercises WHERE name = ? AND deleted_at IS NULL", (name,)
            ).fetchone()
            return row is not None

    def match_exercise(self, name: str, cutoff: float = 0.6) -> str | None:
        exercises = self.get_exercise_list()
        matches = difflib.get_close_matches(name, exercises, n=1, cutoff=cutoff)
        return matches[0] if matches else None

    def get_max_for_exercise(self, user_id: int, exercise: str) -> float | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT MAX(weight_kg) FROM one_rep_maxes WHERE user_id = ? AND exercise = ? AND deleted_at IS NULL",
                (user_id, exercise),
            ).fetchone()
            return row[0] if row and row[0] is not None else None

    def get_by_id(self, user_id: int, entry_id: int) -> OneRepMax | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM one_rep_maxes WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                (entry_id, user_id),
            ).fetchone()
            return self._row_to_model(row) if row else None

    def update(self, user_id: int, entry_id: int, exercise: str, weight_kg: float, recorded_at: date) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE one_rep_maxes SET exercise = ?, weight_kg = ?, recorded_at = ?, updated_at = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                (exercise, weight_kg, recorded_at.isoformat(), datetime.now().isoformat(), entry_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0
