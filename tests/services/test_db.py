"""Tests for services/db.py"""

import sqlite3
from pathlib import Path

from wodplanner.services.db import BUSY_TIMEOUT_MS, get_connection


class TestGetConnection:
    def test_creates_connection(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path)
        assert isinstance(conn, sqlite3.Connection)
        conn.close()

    def test_sets_wal_journal_mode(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path)
        conn.execute("PRAGMA journal_mode")
        row = conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0] == "wal"
        conn.close()

    def test_sets_synchronous_normal(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path)
        row = conn.execute("PRAGMA synchronous").fetchone()
        assert row[0] == 1  # NORMAL
        conn.close()

    def test_enables_foreign_keys(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path)
        row = conn.execute("PRAGMA foreign_keys").fetchone()
        assert row[0] == 1
        conn.close()

    def test_sets_busy_timeout(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path)
        row = conn.execute("PRAGMA busy_timeout").fetchone()
        assert row[0] == BUSY_TIMEOUT_MS
        conn.close()

    def test_sets_row_factory(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path)
        assert conn.row_factory == sqlite3.Row
        conn.close()

    def test_connection_usable_for_queries(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path)
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO test (name) VALUES (?)", ("test_value",))
        conn.commit()
        row = conn.execute("SELECT * FROM test").fetchone()
        assert row["name"] == "test_value"
        conn.close()

    def test_accepts_path_object(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = get_connection(Path(db_path))
        assert isinstance(conn, sqlite3.Connection)
        conn.close()

    def test_creates_file_if_not_exists(self, tmp_path):
        db_path = tmp_path / "new.db"
        assert not db_path.exists()
        conn = get_connection(db_path)
        conn.close()
        assert db_path.exists()
