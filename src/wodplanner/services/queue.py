"""Queue service for managing auto-signup requests."""

import sqlite3
from datetime import datetime
from pathlib import Path

from wodplanner.models.queue import QueuedSignup, QueueStatus


class QueueService:
    """Service for managing the auto-signup queue with SQLite storage."""

    def __init__(self, db_path: str | Path = "wodplanner.db") -> None:
        self.db_path = Path(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signup_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    appointment_id INTEGER NOT NULL,
                    appointment_name TEXT NOT NULL,
                    date_start TEXT NOT NULL,
                    date_end TEXT NOT NULL,
                    signup_opens_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    result_message TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                )
            """)
            conn.commit()

            # Migration: add user_token and user_id columns if missing
            cursor = conn.execute("PRAGMA table_info(signup_queue)")
            columns = {row["name"] for row in cursor.fetchall()}

            if "user_token" not in columns:
                conn.execute("ALTER TABLE signup_queue ADD COLUMN user_token TEXT")
                conn.commit()

            if "user_id" not in columns:
                conn.execute("ALTER TABLE signup_queue ADD COLUMN user_id INTEGER")
                conn.commit()

    def _row_to_model(self, row: sqlite3.Row) -> QueuedSignup:
        """Convert a database row to a QueuedSignup model."""
        return QueuedSignup(
            id=row["id"],
            appointment_id=row["appointment_id"],
            appointment_name=row["appointment_name"],
            date_start=datetime.fromisoformat(row["date_start"]),
            date_end=datetime.fromisoformat(row["date_end"]),
            signup_opens_at=datetime.fromisoformat(row["signup_opens_at"]),
            status=QueueStatus(row["status"]),
            result_message=row["result_message"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            user_token=row["user_token"],
            user_id=row["user_id"],
        )

    def add(self, signup: QueuedSignup) -> QueuedSignup:
        """Add a signup to the queue."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO signup_queue
                (appointment_id, appointment_name, date_start, date_end,
                 signup_opens_at, status, created_at, user_token, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signup.appointment_id,
                    signup.appointment_name,
                    signup.date_start.isoformat(),
                    signup.date_end.isoformat(),
                    signup.signup_opens_at.isoformat(),
                    signup.status,
                    datetime.now().isoformat(),
                    signup.user_token,
                    signup.user_id,
                ),
            )
            conn.commit()
            signup.id = cursor.lastrowid
            signup.created_at = datetime.now()
            return signup

    def get(self, signup_id: int) -> QueuedSignup | None:
        """Get a signup by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM signup_queue WHERE id = ?", (signup_id,)
            ).fetchone()
            if row:
                return self._row_to_model(row)
            return None

    def get_all(self, include_completed: bool = False) -> list[QueuedSignup]:
        """Get all signups in the queue."""
        with self._get_connection() as conn:
            if include_completed:
                rows = conn.execute(
                    "SELECT * FROM signup_queue ORDER BY signup_opens_at"
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM signup_queue
                    WHERE status IN ('pending', 'scheduled')
                    ORDER BY signup_opens_at
                    """
                ).fetchall()
            return [self._row_to_model(row) for row in rows]

    def get_pending(self) -> list[QueuedSignup]:
        """Get all pending signups that need to be scheduled."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM signup_queue WHERE status = 'pending' ORDER BY signup_opens_at"
            ).fetchall()
            return [self._row_to_model(row) for row in rows]

    def update_status(
        self,
        signup_id: int,
        status: QueueStatus,
        result_message: str | None = None,
    ) -> None:
        """Update the status of a signup."""
        with self._get_connection() as conn:
            if status in (QueueStatus.COMPLETED, QueueStatus.FAILED, QueueStatus.WAITLISTED):
                conn.execute(
                    """
                    UPDATE signup_queue
                    SET status = ?, result_message = ?, completed_at = ?
                    WHERE id = ?
                    """,
                    (status, result_message, datetime.now().isoformat(), signup_id),
                )
            else:
                conn.execute(
                    "UPDATE signup_queue SET status = ?, result_message = ? WHERE id = ?",
                    (status, result_message, signup_id),
                )
            conn.commit()

    def delete(self, signup_id: int) -> bool:
        """Delete a signup from the queue."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM signup_queue WHERE id = ?", (signup_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def cancel(self, signup_id: int) -> bool:
        """Cancel a pending signup."""
        signup = self.get(signup_id)
        if signup and signup.status in (QueueStatus.PENDING, QueueStatus.SCHEDULED):
            self.update_status(signup_id, QueueStatus.CANCELLED)
            return True
        return False
