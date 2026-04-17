"""Friends service for managing friend list."""

import sqlite3
from datetime import datetime
from pathlib import Path

from wodplanner.models.friends import Friend


class FriendsService:
    """Service for managing friends with SQLite storage."""

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
                CREATE TABLE IF NOT EXISTS friends (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    appuser_id INTEGER NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    added_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def _row_to_model(self, row: sqlite3.Row) -> Friend:
        """Convert a database row to a Friend model."""
        return Friend(
            id=row["id"],
            appuser_id=row["appuser_id"],
            name=row["name"],
            added_at=datetime.fromisoformat(row["added_at"]),
        )

    def add(self, appuser_id: int, name: str) -> Friend:
        """Add a friend."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO friends (appuser_id, name, added_at)
                VALUES (?, ?, ?)
                ON CONFLICT(appuser_id) DO UPDATE SET name = excluded.name
                """,
                (appuser_id, name, datetime.now().isoformat()),
            )
            conn.commit()

            # Fetch the inserted/updated record
            row = conn.execute(
                "SELECT * FROM friends WHERE appuser_id = ?", (appuser_id,)
            ).fetchone()
            return self._row_to_model(row)

    def get(self, friend_id: int) -> Friend | None:
        """Get a friend by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM friends WHERE id = ?", (friend_id,)
            ).fetchone()
            if row:
                return self._row_to_model(row)
            return None

    def get_by_appuser_id(self, appuser_id: int) -> Friend | None:
        """Get a friend by WodApp user ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM friends WHERE appuser_id = ?", (appuser_id,)
            ).fetchone()
            if row:
                return self._row_to_model(row)
            return None

    def get_all(self) -> list[Friend]:
        """Get all friends."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM friends ORDER BY name"
            ).fetchall()
            return [self._row_to_model(row) for row in rows]

    def get_appuser_ids(self) -> set[int]:
        """Get set of all friend appuser IDs for quick lookup."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT appuser_id FROM friends").fetchall()
            return {row["appuser_id"] for row in rows}

    def delete(self, friend_id: int) -> bool:
        """Delete a friend by ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM friends WHERE id = ?", (friend_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_by_appuser_id(self, appuser_id: int) -> bool:
        """Delete a friend by WodApp user ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM friends WHERE appuser_id = ?", (appuser_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
