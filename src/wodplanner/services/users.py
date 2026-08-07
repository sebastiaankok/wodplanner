"""User service — single source of truth for user identity.

The `users` table replaces the user-scoped columns previously stored in the
`preferences` table (my_appuser_id, tracking_disabled, avatar_filename) and is
referenced by every user-scoped table. Rows are created at login time (see
`auth.login`) and updated lazily when the user's `appuser_id` is discovered via
the people modal.
"""

import json
import sqlite3
from datetime import datetime

from wodplanner.models.user import User
from wodplanner.services import migrations
from wodplanner.services.base import BaseService
from wodplanner.utils.dates import parse_iso_datetime


def _user_scoped_tables() -> list[tuple[str, str]]:
    return [
        ("preferences", "user_id"),
        ("one_rep_maxes", "user_id"),
        ("benchmark_results", "user_id"),
        ("subscription_events", "user_id"),
        ("friends", "owner_user_id"),
    ]


def _migrate_v800(conn: sqlite3.Connection) -> None:
    """Create users table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            appuser_id INTEGER UNIQUE,
            gym_id INTEGER,
            display_name TEXT,
            avatar_filename TEXT,
            tracking_disabled INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _user_pref(conn: sqlite3.Connection, user_id: int, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM preferences WHERE user_id = ? AND key = ?", (user_id, key)
    ).fetchone()
    return row[0] if row else None


def _migrate_v801(conn: sqlite3.Connection) -> None:
    """Populate users from existing user-scoped tables; clean migrated prefs."""
    user_ids: set[int] = set()
    for table, column in _user_scoped_tables():
        if migrations.table_exists(conn, table):
            rows = conn.execute(
                f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL"
            ).fetchall()
            user_ids.update(int(row[0]) for row in rows if row[0] is not None)

    now = datetime.now().isoformat()
    for user_id in user_ids:
        appuser_id_raw = _user_pref(conn, user_id, "my_appuser_id")
        appuser_id = int(appuser_id_raw) if appuser_id_raw else None
        tracking_raw = _user_pref(conn, user_id, "tracking_disabled")
        tracking_disabled = 1 if tracking_raw and json.loads(tracking_raw) else 0
        avatar = _user_pref(conn, user_id, "avatar_filename")
        conn.execute(
            """
            INSERT OR IGNORE INTO users
                (id, appuser_id, gym_id, display_name, avatar_filename,
                 tracking_disabled, created_at, updated_at)
            VALUES (?, ?, NULL, NULL, ?, ?, ?, ?)
            """,
            (user_id, appuser_id, avatar, tracking_disabled, now, now),
        )

    conn.execute(
        "DELETE FROM preferences WHERE key IN ('my_appuser_id', 'tracking_disabled', 'avatar_filename')"
    )


def _migrate_v802(conn: sqlite3.Connection) -> None:
    """Recreate preferences with FK to users (keeps only UI settings)."""
    if migrations.has_fk_to(conn, "preferences", "users") and migrations.has_column(
        conn, "preferences", "value"
    ):
        return
    with migrations.fk_disabled(conn):
        conn.execute("ALTER TABLE preferences RENAME TO preferences_old")
        conn.execute(
            """
            CREATE TABLE preferences (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (user_id, key)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO preferences (user_id, key, value)
            SELECT user_id, key, value FROM preferences_old
            """
        )
        conn.execute("DROP TABLE preferences_old")


migrations.register(800, "create users table", _migrate_v800)
migrations.register(801, "populate users from existing data", _migrate_v801)
migrations.register(802, "recreate preferences with FK to users", _migrate_v802)


class UserService(BaseService):
    """SQLite-backed user identity storage."""

    def _row_to_model(self, row: sqlite3.Row) -> User:
        return User(
            id=row["id"],
            appuser_id=row["appuser_id"],
            gym_id=row["gym_id"],
            display_name=row["display_name"],
            avatar_filename=row["avatar_filename"],
            tracking_disabled=bool(row["tracking_disabled"]),
            created_at=parse_iso_datetime(row["created_at"]),
            updated_at=parse_iso_datetime(row["updated_at"]),
        )

    def upsert(
        self, user_id: int, appuser_id: int | None, gym_id: int | None, display_name: str | None
    ) -> None:
        """Insert or refresh a user from session data.

        Skips the write when no values have changed, avoiding unnecessary
        SQLite write-lock contention on every request.

        Updates gym_id and display_name on every call.  appuser_id is only
        updated when a non-NULL value is provided, so a later request with a
        NULL session appuser_id won't clobber a previously discovered Member ID.
        Never overwrites the user-managed tracking_disabled or avatar_filename.
        """
        existing = self.get(user_id)
        if existing is not None:
            resolved_appuser_id = appuser_id if appuser_id is not None else existing.appuser_id
            if (
                existing.display_name == display_name
                and existing.gym_id == gym_id
                and existing.appuser_id == resolved_appuser_id
            ):
                return
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO users
                    (id, appuser_id, gym_id, display_name, tracking_disabled,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    appuser_id = COALESCE(excluded.appuser_id, users.appuser_id),
                    gym_id = excluded.gym_id,
                    display_name = excluded.display_name,
                    updated_at = excluded.updated_at
                """,
                (user_id, appuser_id, gym_id, display_name, now, now),
            )
            conn.commit()

    def get(self, user_id: int) -> User | None:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._row_to_model(row) if row else None

    def get_avatar_filename(self, user_id: int) -> str | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT avatar_filename FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return row[0] if row else None

    def get_avatar_filenames_by_appuser_ids(
        self, appuser_ids: list[int]
    ) -> dict[int, str | None]:
        if not appuser_ids:
            return {}
        with self._get_connection() as conn:
            placeholders = ",".join("?" * len(appuser_ids))
            rows = conn.execute(
                f"SELECT appuser_id, avatar_filename FROM users WHERE appuser_id IN ({placeholders})",
                appuser_ids,
            ).fetchall()
        result: dict[int, str | None] = {}
        for row in rows:
            if row["avatar_filename"]:
                result[row["appuser_id"]] = row["avatar_filename"]
        return result

    def is_tracking_disabled(self, user_id: int) -> bool:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT tracking_disabled FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return bool(row[0]) if row else False

    def set_tracking_disabled(self, user_id: int, disabled: bool) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE users SET tracking_disabled = ?, updated_at = ? WHERE id = ?",
                (int(disabled), datetime.now().isoformat(), user_id),
            )
            conn.commit()

    def set_avatar_filename(self, user_id: int, filename: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE users SET avatar_filename = ?, updated_at = ? WHERE id = ?",
                (filename, datetime.now().isoformat(), user_id),
            )
            conn.commit()

    def delete_avatar_filename(self, user_id: int) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE users SET avatar_filename = NULL, updated_at = ? WHERE id = ?",
                (datetime.now().isoformat(), user_id),
            )
            conn.commit()
