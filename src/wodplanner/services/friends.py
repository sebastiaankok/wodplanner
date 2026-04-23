"""Friends service for managing friend list."""

import sqlite3
from datetime import datetime

from wodplanner.models.friends import Friend
from wodplanner.services import migrations
from wodplanner.services.base import BaseService
from wodplanner.utils.dates import parse_iso_datetime


def _migrate_v200(conn: sqlite3.Connection) -> None:
    """Create friends table; migrate old single-column UNIQUE(appuser_id) schema."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS friends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_user_id INTEGER NOT NULL DEFAULT 0,
            appuser_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            added_at TEXT NOT NULL,
            UNIQUE(owner_user_id, appuser_id)
        )
        """
    )
    table_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='friends'"
    ).fetchone()[0]
    needs_migration = (
        "owner_user_id" not in table_sql or "UNIQUE(owner_user_id" not in table_sql
    )
    if needs_migration:
        conn.execute("ALTER TABLE friends RENAME TO friends_old")
        conn.execute(
            """
            CREATE TABLE friends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_user_id INTEGER NOT NULL DEFAULT 0,
                appuser_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                added_at TEXT NOT NULL,
                UNIQUE(owner_user_id, appuser_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO friends (id, owner_user_id, appuser_id, name, added_at)
            SELECT id, 0, appuser_id, name, added_at FROM friends_old
            """
        )
        conn.execute("DROP TABLE friends_old")


migrations.register(200, "create friends table (owner-scoped)", _migrate_v200)


class FriendsService(BaseService):
    """Service for managing friends with SQLite storage."""

    def _row_to_model(self, row: sqlite3.Row) -> Friend:
        return Friend(
            id=row["id"],
            owner_user_id=row["owner_user_id"],
            appuser_id=row["appuser_id"],
            name=row["name"],
            added_at=parse_iso_datetime(row["added_at"]),
        )

    def add(self, owner_user_id: int, appuser_id: int, name: str) -> Friend:
        """Add a friend for the given owner."""
        with self._get_connection() as conn:
            row = conn.execute(
                """
                INSERT INTO friends (owner_user_id, appuser_id, name, added_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(owner_user_id, appuser_id) DO UPDATE SET name = excluded.name
                RETURNING *
                """,
                (owner_user_id, appuser_id, name, datetime.now().isoformat()),
            ).fetchone()
            conn.commit()
            return self._row_to_model(row)

    def get(self, owner_user_id: int, friend_id: int) -> Friend | None:
        """Get a friend by ID, scoped to owner."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM friends WHERE id = ? AND owner_user_id = ?",
                (friend_id, owner_user_id),
            ).fetchone()
            return self._row_to_model(row) if row else None

    def get_by_appuser_id(self, owner_user_id: int, appuser_id: int) -> Friend | None:
        """Get a friend by WodApp user ID, scoped to owner."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM friends WHERE owner_user_id = ? AND appuser_id = ?",
                (owner_user_id, appuser_id),
            ).fetchone()
            return self._row_to_model(row) if row else None

    def get_all(self, owner_user_id: int) -> list[Friend]:
        """Get all friends for owner."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM friends WHERE owner_user_id = ? ORDER BY name",
                (owner_user_id,),
            ).fetchall()
            return [self._row_to_model(row) for row in rows]

    def get_appuser_ids(self, owner_user_id: int) -> set[int]:
        """Get set of friend appuser IDs for quick lookup, scoped to owner."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT appuser_id FROM friends WHERE owner_user_id = ?",
                (owner_user_id,),
            ).fetchall()
            return {row["appuser_id"] for row in rows}

    def delete(self, owner_user_id: int, friend_id: int) -> bool:
        """Delete a friend by ID, scoped to owner."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM friends WHERE id = ? AND owner_user_id = ?",
                (friend_id, owner_user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_by_appuser_id(self, owner_user_id: int, appuser_id: int) -> bool:
        """Delete a friend by WodApp user ID, scoped to owner."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM friends WHERE owner_user_id = ? AND appuser_id = ?",
                (owner_user_id, appuser_id),
            )
            conn.commit()
            return cursor.rowcount > 0
