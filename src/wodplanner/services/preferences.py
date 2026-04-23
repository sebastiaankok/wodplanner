"""User preferences storage service."""

import json
import sqlite3
from dataclasses import dataclass, field

from wodplanner.services import migrations
from wodplanner.services.base import BaseService


@dataclass
class UserPreferences:
    """User preferences."""
    hidden_class_types: list[str] = field(default_factory=list)


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
        return json.loads(value)

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

    def get_dismissed_tooltips(self, user_id: int) -> list[str]:
        value = self._get(user_id, "dismissed_tooltips", "[]")
        return json.loads(value)

    def dismiss_tooltip(self, user_id: int, tooltip_id: str) -> None:
        dismissed = self.get_dismissed_tooltips(user_id)
        if tooltip_id not in dismissed:
            dismissed.append(tooltip_id)
            self._set(user_id, "dismissed_tooltips", json.dumps(dismissed))

    def get_all(self, user_id: int) -> UserPreferences:
        return UserPreferences(
            hidden_class_types=self.get_hidden_class_types(user_id),
        )
