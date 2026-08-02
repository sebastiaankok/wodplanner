"""User preferences storage service."""

import json
import sqlite3
from dataclasses import dataclass, field
from typing import cast

from wodplanner.services import migrations
from wodplanner.services.base import BaseService


@dataclass
class UserPreferences:
    """User preferences."""
    hidden_class_types: list[str] = field(default_factory=list)
    dismissed_tooltips: list[str] = field(default_factory=list)
    tracking_disabled: bool = False


def _migrate_v300(conn: sqlite3.Connection) -> None:
    """Create preferences table; migrate old single-column key schema."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS preferences (
            user_id INTEGER NOT NULL DEFAULT 0,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (user_id, key)
        )
        """
    )
    table_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='preferences'"
    ).fetchone()[0]
    if "user_id" not in table_sql:
        conn.execute("ALTER TABLE preferences RENAME TO preferences_old")
        conn.execute(
            """
            CREATE TABLE preferences (
                user_id INTEGER NOT NULL DEFAULT 0,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (user_id, key)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO preferences (user_id, key, value)
            SELECT 0, key, value FROM preferences_old
            """
        )
        conn.execute("DROP TABLE preferences_old")


migrations.register(300, "create preferences table (user-scoped)", _migrate_v300)


class PreferencesService(BaseService):
    """SQLite-backed preferences storage."""

    def _get(self, user_id: int, key: str, default: str = "") -> str:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM preferences WHERE user_id = ? AND key = ?",
                (user_id, key),
            ).fetchone()
        return row[0] if row else default

    def _set(self, user_id: int, key: str, value: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO preferences (user_id, key, value) VALUES (?, ?, ?)",
                (user_id, key, value),
            )
            conn.commit()

    def get_hidden_class_types(self, user_id: int) -> list[str]:
        value = self._get(user_id, "hidden_class_types", "[]")
        return cast("list[str]", json.loads(value))

    def set_hidden_class_types(self, user_id: int, types: list[str]) -> None:
        self._set(user_id, "hidden_class_types", json.dumps(types))

    def toggle_hidden_class_type(self, user_id: int, class_type: str) -> list[str]:
        hidden = self.get_hidden_class_types(user_id)
        if class_type in hidden:
            hidden.remove(class_type)
        else:
            hidden.append(class_type)
        self.set_hidden_class_types(user_id, hidden)
        return hidden

    def get_my_appuser_id(self, user_id: int) -> int | None:
        value = self._get(user_id, "my_appuser_id", "")
        return int(value) if value else None

    def set_my_appuser_id(self, user_id: int, appuser_id: int) -> None:
        self._set(user_id, "my_appuser_id", str(appuser_id))

    def get_dismissed_tooltips(self, user_id: int) -> list[str]:
        value = self._get(user_id, "dismissed_tooltips", "[]")
        return cast("list[str]", json.loads(value))

    def dismiss_tooltip(self, user_id: int, tooltip_id: str) -> None:
        dismissed = self.get_dismissed_tooltips(user_id)
        if tooltip_id not in dismissed:
            dismissed.append(tooltip_id)
            self._set(user_id, "dismissed_tooltips", json.dumps(dismissed))

    def reset_tooltips(self, user_id: int) -> None:
        self._set(user_id, "dismissed_tooltips", "[]")

    def is_tracking_disabled(self, user_id: int) -> bool:
        value = self._get(user_id, "tracking_disabled", "false")
        return cast("bool", json.loads(value))

    def set_tracking_disabled(self, user_id: int, disabled: bool) -> None:
        self._set(user_id, "tracking_disabled", json.dumps(disabled))

    def get_for_user(self, user_id: int) -> UserPreferences:
        """Get all preferences for a user in a single query."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT key, value FROM preferences WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        prefs = UserPreferences()
        for row in rows:
            key, value = row["key"], row["value"]
            if key == "hidden_class_types":
                prefs.hidden_class_types = json.loads(value)
            elif key == "dismissed_tooltips":
                prefs.dismissed_tooltips = json.loads(value)
            elif key == "tracking_disabled":
                prefs.tracking_disabled = json.loads(value)
        return prefs

    def get_all(self, user_id: int) -> UserPreferences:
        return self.get_for_user(user_id)

    def get_avatar_filename(self, user_id: int) -> str | None:
        value = self._get(user_id, "avatar_filename", "")
        return value if value else None

    def set_avatar_filename(self, user_id: int, filename: str) -> None:
        self._set(user_id, "avatar_filename", filename)

    def delete_avatar_filename(self, user_id: int) -> None:
        """Remove the avatar filename preference for a user."""
        with self._get_connection() as conn:
            conn.execute(
                "DELETE FROM preferences WHERE user_id = ? AND key = 'avatar_filename'",
                (user_id,),
            )
            conn.commit()

    def get_avatar_filenames(self, user_ids: list[int]) -> dict[int, str]:
        if not user_ids:
            return {}
        with self._get_connection() as conn:
            placeholders = ",".join("?" * len(user_ids))
            rows = conn.execute(
                f"SELECT user_id, value FROM preferences WHERE user_id IN ({placeholders}) AND key = 'avatar_filename'",
                user_ids,
            ).fetchall()
        return {row["user_id"]: row["value"] for row in rows}

    def get_avatar_filenames_by_appuser_ids(self, appuser_ids: list[int]) -> dict[int, str | None]:
        """Get avatar filenames keyed by WodApp appuser_id.

        First tries direct lookup by appuser_id. For unfound IDs, falls back
        to reverse-mapping via my_appuser_id preferences (user_id → appuser_id)
        to find avatars stored only under the session user_id.
        """
        if not appuser_ids:
            return {}

        result: dict[int, str | None] = {uid: None for uid in appuser_ids}

        with self._get_connection() as conn:
            # 1. Direct lookup by appuser_id
            placeholders = ",".join("?" * len(appuser_ids))
            rows = conn.execute(
                f"SELECT user_id, value FROM preferences WHERE user_id IN ({placeholders}) AND key = 'avatar_filename'",
                appuser_ids,
            ).fetchall()
            for row in rows:
                result[row["user_id"]] = row["value"]

            # 2. For unfound IDs, reverse-map through my_appuser_id
            unfound = [uid for uid in appuser_ids if result[uid] is None]
            if unfound:
                placeholders = ",".join("?" * len(unfound))
                rows = conn.execute(
                    f"SELECT user_id, value FROM preferences WHERE key = 'my_appuser_id' AND value IN ({placeholders})",
                    unfound,
                ).fetchall()
                mapped_session_ids = [int(row["value"]) for row in rows]
                if mapped_session_ids:
                    placeholders = ",".join("?" * len(mapped_session_ids))
                    avatar_rows = conn.execute(
                        f"SELECT user_id, value FROM preferences WHERE user_id IN ({placeholders}) AND key = 'avatar_filename'",
                        mapped_session_ids,
                    ).fetchall()
                    session_to_avatar = {row["user_id"]: row["value"] for row in avatar_rows}
                    for row in rows:
                        session_id = int(row["value"])
                        avatar = session_to_avatar.get(session_id)
                        if avatar:
                            appuser_id = row["user_id"]
                            result[int(appuser_id)] = avatar

        return result
