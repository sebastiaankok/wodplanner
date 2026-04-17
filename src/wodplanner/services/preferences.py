"""User preferences storage service."""

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class UserPreferences:
    """User preferences."""
    hidden_class_types: list[str] = field(default_factory=list)


class PreferencesService:
    """SQLite-backed preferences storage."""

    def __init__(self, db_path: str = "wodplanner.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database table."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def _get(self, key: str, default: str = "") -> str:
        """Get a preference value."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM preferences WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else default

    def _set(self, key: str, value: str) -> None:
        """Set a preference value."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO preferences (key, value) VALUES (?, ?)",
            (key, value),
        )
        conn.commit()
        conn.close()

    def get_hidden_class_types(self) -> list[str]:
        """Get list of hidden class types."""
        value = self._get("hidden_class_types", "[]")
        return json.loads(value)

    def set_hidden_class_types(self, types: list[str]) -> None:
        """Set list of hidden class types."""
        self._set("hidden_class_types", json.dumps(types))

    def toggle_hidden_class_type(self, class_type: str) -> list[str]:
        """Toggle a class type visibility. Returns updated list."""
        hidden = self.get_hidden_class_types()
        if class_type in hidden:
            hidden.remove(class_type)
        else:
            hidden.append(class_type)
        self.set_hidden_class_types(hidden)
        return hidden

    def get_all(self) -> UserPreferences:
        """Get all preferences."""
        return UserPreferences(
            hidden_class_types=self.get_hidden_class_types(),
        )
