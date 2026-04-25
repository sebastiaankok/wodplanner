"""Tests for services/base.py"""

import sqlite3
from pathlib import Path

from wodplanner.services.base import BaseService


class TestBaseService:
    def test_db_path_stored_as_path(self):
        svc = BaseService("test.db")
        assert isinstance(svc.db_path, Path)
        assert svc.db_path == Path("test.db")

    def test_db_path_accepts_path_object(self, tmp_path):
        db_path = tmp_path / "test.db"
        svc = BaseService(db_path)
        assert svc.db_path == db_path

    def test_get_connection_returns_connection(self, tmp_path):
        db_path = tmp_path / "test.db"
        svc = BaseService(db_path)
        conn = svc._get_connection()
        assert isinstance(conn, sqlite3.Connection)
        conn.close()

    def test_get_connection_sets_pragmas(self, tmp_path):
        db_path = tmp_path / "test.db"
        svc = BaseService(db_path)
        conn = svc._get_connection()
        row = conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0] == "wal"
        conn.close()

    def test_default_db_path(self):
        svc = BaseService()
        assert svc.db_path == Path("wodplanner.db")

    def test_str_db_path_converted(self):
        svc = BaseService("/tmp/test.db")
        assert svc.db_path == Path("/tmp/test.db")
