"""Session service for browser-based authentication."""

import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from wodplanner.models.auth import AuthSession


class SessionService:
    """Service for managing browser sessions with SQLite storage."""

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
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    token TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    firstname TEXT NOT NULL,
                    gym_id INTEGER NOT NULL,
                    gym_name TEXT NOT NULL,
                    agenda_id INTEGER,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def create(
        self,
        auth_session: AuthSession,
        expire_days: int = 7,
    ) -> str:
        """
        Create a new browser session from an authenticated WodApp session.

        Args:
            auth_session: The authenticated session from WodApp login
            expire_days: Number of days until the session expires

        Returns:
            The session ID to store in the cookie
        """
        session_id = secrets.token_urlsafe(32)
        now = datetime.now()
        expires_at = now + timedelta(days=expire_days)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions
                (session_id, token, user_id, username, firstname, gym_id, gym_name, agenda_id, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    auth_session.token,
                    auth_session.user_id,
                    auth_session.username,
                    auth_session.firstname,
                    auth_session.gym_id,
                    auth_session.gym_name,
                    auth_session.agenda_id,
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            conn.commit()

        return session_id

    def get(self, session_id: str) -> AuthSession | None:
        """
        Get an AuthSession from a session ID.

        Args:
            session_id: The session ID from the cookie

        Returns:
            AuthSession if valid and not expired, None otherwise
        """
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()

            if not row:
                return None

            # Check if expired
            expires_at = datetime.fromisoformat(row["expires_at"])
            if datetime.now() > expires_at:
                self.delete(session_id)
                return None

            return AuthSession(
                token=row["token"],
                user_id=row["user_id"],
                username=row["username"],
                firstname=row["firstname"],
                gym_id=row["gym_id"],
                gym_name=row["gym_name"],
                agenda_id=row["agenda_id"],
            )

    def delete(self, session_id: str) -> bool:
        """
        Delete a session.

        Args:
            session_id: The session ID to delete

        Returns:
            True if a session was deleted, False otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def cleanup_expired(self) -> int:
        """
        Delete all expired sessions.

        Returns:
            Number of sessions deleted
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE expires_at < ?",
                (datetime.now().isoformat(),),
            )
            conn.commit()
            return cursor.rowcount
