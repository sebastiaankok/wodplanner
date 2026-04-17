"""One rep max service."""

import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

from wodplanner.models.one_rep_max import OneRepMax


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
    for m in re.finditer(r'1rm\s+(.+?)(?=\s+[A-Z]\.\s|\s*$)', text, re.IGNORECASE):
        preceding = text[max(0, m.start() - 6):m.start()]
        if not re.search(r'\d+%\s*$', preceding):
            # Strip parenthetical annotations like (2x 20kg)
            name = re.sub(r'\s*\([^)]*\)', '', m.group(1)).strip()
            if name:
                results.append(name)
    return results


class OneRepMaxService:
    def __init__(self, db_path: str | Path = "wodplanner.db") -> None:
        self.db_path = Path(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
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
            cursor = conn.execute(
                "INSERT INTO one_rep_maxes (user_id, exercise, weight_kg, recorded_at, notes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, exercise.strip(), weight_kg, recorded_at.isoformat(), notes, datetime.now().isoformat()),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM one_rep_maxes WHERE id = ?", (cursor.lastrowid,)).fetchone()
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
