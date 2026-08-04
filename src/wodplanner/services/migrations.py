"""Schema migration registry.

Services register migrations at import time. The app lifespan handler (and CLI
entry points) call ensure_migrations(db_path) once to apply any pending
migrations.

Each migration has a unique integer version, a description, and either a SQL
string or a callable that takes a sqlite3.Connection. The schema_migrations
table records applied versions so reruns are no-ops.

Version ranges per service (keep migrations grouped and avoid collisions):
    100-199  schedule
    200-299  friends
    300-399  preferences
    400-499  one_rep_max
    600-699  benchmark
    700-799  subscription_tracker
    800-899  users (single source of truth for user identity)
"""

from __future__ import annotations

import contextlib
import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator, Union

from wodplanner.services.db import get_connection

logger = logging.getLogger(__name__)

MigrationFn = Callable[[sqlite3.Connection], None]
MigrationSql = Union[str, MigrationFn]


@dataclass(frozen=True)
class _Entry:
    version: int
    description: str
    sql: MigrationSql


_registry: list[_Entry] = []
_applied_paths: set[Path] = set()
_lock = threading.Lock()


@contextlib.contextmanager
def fk_disabled(conn: sqlite3.Connection) -> Iterator[None]:
    """Temporarily disable FK enforcement so recreate-and-copy migrations can
    preserve otherwise-orphaned rows. FK is re-enabled and committed on exit."""
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        yield
    finally:
        conn.commit()
        conn.execute("PRAGMA foreign_keys=ON")
        conn.commit()


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    return column in cols


def has_fk_to(conn: sqlite3.Connection, table: str, parent: str) -> bool:
    return any(r["table"] == parent for r in conn.execute(f"PRAGMA foreign_key_list({table})"))


def register(version: int, description: str, sql: MigrationSql) -> None:
    """Register a migration. Version must be unique across the whole app."""
    for entry in _registry:
        if entry.version == version:
            if entry.description == description and entry.sql is sql:
                return
            raise ValueError(
                f"migration version {version} already registered: {entry.description!r}"
            )
    _registry.append(_Entry(version, description, sql))


def run_all(conn: sqlite3.Connection) -> list[int]:
    """Apply pending migrations against an open connection. Returns versions run."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    conn.commit()

    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    ran: list[int] = []
    for entry in sorted(_registry, key=lambda e: e.version):
        if entry.version in applied:
            continue
        if callable(entry.sql):
            entry.sql(conn)
        else:
            conn.executescript(entry.sql)
        conn.execute(
            "INSERT INTO schema_migrations (version, description, applied_at) VALUES (?, ?, ?)",
            (entry.version, entry.description, datetime.now().isoformat()),
        )
        conn.commit()
        ran.append(entry.version)
        logger.info("Applied migration %d: %s", entry.version, entry.description)
    return ran


def _import_services_for_registration() -> None:
    """Import service modules so their register() calls execute."""
    # Local imports avoid a circular import at module load time.
    from wodplanner.services import (  # noqa: F401
        benchmark,
        friends,
        one_rep_max,
        preferences,
        schedule,
        subscription_tracker,
        users,
    )


def ensure_migrations(db_path: str | Path) -> list[int]:
    """Apply pending migrations once per process per db_path. Idempotent."""
    _import_services_for_registration()
    path = Path(db_path).resolve()
    with _lock:
        if path in _applied_paths:
            return []
        with get_connection(path) as conn:
            ran = run_all(conn)
        _applied_paths.add(path)
        return ran


def _reset_for_tests() -> None:
    """Clear the applied-paths cache so tests can re-run migrations."""
    with _lock:
        _applied_paths.clear()
