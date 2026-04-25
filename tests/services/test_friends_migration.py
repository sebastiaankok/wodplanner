"""Tests for friends._migrate_v200 ALTER branch (legacy schema migration)."""

import sqlite3

from wodplanner.services import migrations
from wodplanner.services.friends import FriendsService, _migrate_v200


class TestFriendsMigrationAlter:
    def test_migrates_old_schema_preserves_rows(self, tmp_path):
        db = tmp_path / "legacy.db"
        # Create old-schema friends table (no owner_user_id, UNIQUE(appuser_id))
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE friends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                appuser_id INTEGER NOT NULL UNIQUE,
                name TEXT NOT NULL,
                added_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO friends (appuser_id, name, added_at) VALUES (?, ?, ?)",
            (123, "OldFriend", "2026-04-25T10:00:00"),
        )
        conn.commit()

        # Run migration
        _migrate_v200(conn)
        conn.commit()
        conn.close()

        # Confirm new schema + row preserved with owner_user_id=0
        migrations._reset_for_tests()
        svc = FriendsService(db)
        rows = svc.get_all(owner_user_id=0)
        assert len(rows) == 1
        assert rows[0].appuser_id == 123
        assert rows[0].name == "OldFriend"
