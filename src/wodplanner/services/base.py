"""Base class for SQLite-backed services."""

import sqlite3
from pathlib import Path

from wodplanner.services.db import get_connection


class BaseService:
    """Shared __init__ and connection factory for SQLite-backed services.

    Schema setup is handled by the migration registry (services.migrations),
    applied once per process via ensure_migrations() — not by service __init__.
    """

    def __init__(self, db_path: str | Path = "wodplanner.db") -> None:
        self.db_path = Path(db_path)

    def _get_connection(self) -> sqlite3.Connection:
        return get_connection(self.db_path)
