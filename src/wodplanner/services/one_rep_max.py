"""One rep max service."""

import difflib
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

from wodplanner.models.one_rep_max import OneRepMax
from wodplanner.services.db import get_connection

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
    # Capture up to next exercise letter (e.g. "B.") or end of line
    for m in re.finditer(r'1rm\s+(.+?)(?=\s+[A-Z]\.\s|\s*$)', text, re.IGNORECASE | re.MULTILINE):
        preceding = text[max(0, m.start() - 6):m.start()]
        if not re.search(r'\d+%\s*$', preceding):
            # Strip parenthetical annotations, collapse internal whitespace/newlines
            name = re.sub(r'\s*\([^)]*\)', '', m.group(1))
            name = re.sub(r'\s+', ' ', name).strip()
            if name:
                results.append(name)
    return results


class OneRepMaxService:
    def __init__(self, db_path: str | Path = "wodplanner.db") -> None:
        self.db_path = Path(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return get_connection(self.db_path)

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS exercises (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS one_rep_maxes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    exercise TEXT NOT NULL,
                    weight_kg REAL NOT NULL,
                    recorded_at TEXT NOT NULL,
                    notes TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            if conn.execute("SELECT COUNT(*) FROM exercises").fetchone()[0] == 0:
                conn.executemany(
                    "INSERT OR IGNORE INTO exercises (name, created_at) VALUES (?, ?)",
                    [(name, datetime.now().isoformat()) for name in _SEED_EXERCISES],
                )
            conn.commit()

    def _row_to_model(self, row: sqlite3.Row) -> OneRepMax:
        return OneRepMax(
            id=row["id"],
            user_id=row["user_id"],
            exercise=row["exercise"],
            weight_kg=row["weight_kg"],
            recorded_at=date.fromisoformat(row["recorded_at"]),
            notes=row["notes"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def add(self, user_id: int, exercise: str, weight_kg: float, recorded_at: date, notes: str | None = None) -> OneRepMax:
        with self._get_connection() as conn:
            row = conn.execute(
                "INSERT INTO one_rep_maxes (user_id, exercise, weight_kg, recorded_at, notes, created_at) VALUES (?, ?, ?, ?, ?, ?) RETURNING *",
                (user_id, exercise.strip(), weight_kg, recorded_at.isoformat(), notes, datetime.now().isoformat()),
            ).fetchone()
            conn.commit()
            return self._row_to_model(row)

    def get_all(self, user_id: int) -> list[OneRepMax]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM one_rep_maxes WHERE user_id = ? ORDER BY recorded_at DESC, created_at DESC",
                (user_id,),
            ).fetchall()
            return [self._row_to_model(row) for row in rows]

    def get_for_exercise(self, user_id: int, exercise: str) -> list[OneRepMax]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM one_rep_maxes WHERE user_id = ? AND exercise = ? ORDER BY recorded_at DESC",
                (user_id, exercise),
            ).fetchall()
            return [self._row_to_model(row) for row in rows]

    def get_exercises(self, user_id: int) -> list[str]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT exercise FROM one_rep_maxes WHERE user_id = ? ORDER BY exercise",
                (user_id,),
            ).fetchall()
            return [row["exercise"] for row in rows]

    def delete(self, user_id: int, entry_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM one_rep_maxes WHERE id = ? AND user_id = ?",
                (entry_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_exercise_list(self) -> list[str]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT name FROM exercises ORDER BY name").fetchall()
            return [row["name"] for row in rows]

    def add_exercise(self, name: str) -> bool:
        """Add exercise to list. Returns False if already exists."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO exercises (name, created_at) VALUES (?, ?)",
                    (name.strip(), datetime.now().isoformat()),
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False

    def validate_exercise(self, name: str) -> bool:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM exercises WHERE name = ?", (name,)
            ).fetchone()
            return row is not None

    def match_exercise(self, name: str, cutoff: float = 0.6) -> str | None:
        exercises = self.get_exercise_list()
        matches = difflib.get_close_matches(name, exercises, n=1, cutoff=cutoff)
        return matches[0] if matches else None

    def get_max_for_exercise(self, user_id: int, exercise: str) -> float | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT MAX(weight_kg) FROM one_rep_maxes WHERE user_id = ? AND exercise = ?",
                (user_id, exercise),
            ).fetchone()
            return row[0] if row and row[0] is not None else None
