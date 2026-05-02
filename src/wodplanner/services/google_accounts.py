"""Database service for Google Calendar sync state.

Version range 500-599.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from wodplanner.models.google import GoogleAccount, SyncedEvent
from wodplanner.services import crypto, migrations
from wodplanner.services.base import BaseService
from wodplanner.services.google_oauth import refresh_access_token


def _migrate_v500(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS google_accounts (
            user_id         INTEGER PRIMARY KEY,
            google_email    TEXT NOT NULL,
            access_token    TEXT NOT NULL,
            refresh_token   TEXT NOT NULL,
            token_expiry    TEXT,
            scopes          TEXT NOT NULL DEFAULT '',
            calendar_id     TEXT,
            calendar_summary TEXT,
            sync_enabled    INTEGER NOT NULL DEFAULT 0,
            last_sync_at    TEXT,
            last_sync_status TEXT,
            created_at      TEXT NOT NULL
        )
        """
    )


def _migrate_v501(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS synced_events (
            user_id          INTEGER NOT NULL,
            id_appointment   INTEGER NOT NULL,
            google_event_id  TEXT NOT NULL,
            calendar_id      TEXT NOT NULL,
            date_start       TEXT NOT NULL,
            date_end         TEXT NOT NULL,
            name             TEXT NOT NULL,
            etag             TEXT,
            synced_at        TEXT NOT NULL,
            PRIMARY KEY (user_id, id_appointment)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_synced_events_user ON synced_events (user_id)"
    )


def _migrate_v502(conn: sqlite3.Connection) -> None:
    """Add encrypted WodApp session for background periodic sync."""
    try:
        conn.execute(
            "ALTER TABLE google_accounts ADD COLUMN wodapp_session_enc TEXT"
        )
    except Exception:
        pass  # Column already exists on re-migration


migrations.register(500, "create google_accounts table", _migrate_v500)
migrations.register(501, "create synced_events table", _migrate_v501)
migrations.register(502, "add wodapp_session_enc to google_accounts", _migrate_v502)


class GoogleAccountsService(BaseService):
    """DB service for google_accounts and synced_events tables."""

    def __init__(self, db_path: str | Path = "wodplanner.db", enc_key: bytes | None = None) -> None:
        super().__init__(db_path)
        self._enc_key = enc_key

    def get_valid_token(self, account: GoogleAccount) -> str:
        """Return a valid access token, refreshing via refresh_token when near expiry."""
        raw_token = crypto.decrypt(account.access_token, self._enc_key)  # type: ignore[arg-type]

        if account.token_expiry:
            expiry = datetime.fromisoformat(account.token_expiry)
            if datetime.now() + timedelta(minutes=5) >= expiry:
                raw_refresh = crypto.decrypt(account.refresh_token, self._enc_key)  # type: ignore[arg-type]
                from wodplanner.app.config import settings

                new_token, new_expiry = refresh_access_token(
                    raw_refresh,
                    settings.google_client_id,  # type: ignore[arg-type]
                    settings.google_client_secret,  # type: ignore[arg-type]
                )
                self.update_tokens(
                    account.user_id,
                    crypto.encrypt(new_token, self._enc_key),  # type: ignore[arg-type]
                    new_expiry,
                )
                return new_token

        return raw_token

    def _row_to_account(self, row: sqlite3.Row) -> GoogleAccount:
        return GoogleAccount(
            user_id=row["user_id"],
            google_email=row["google_email"],
            access_token=row["access_token"],
            refresh_token=row["refresh_token"],
            token_expiry=row["token_expiry"],
            scopes=row["scopes"],
            calendar_id=row["calendar_id"],
            calendar_summary=row["calendar_summary"],
            sync_enabled=bool(row["sync_enabled"]),
            last_sync_at=row["last_sync_at"],
            last_sync_status=row["last_sync_status"],
            created_at=row["created_at"],
        )

    def _row_to_event(self, row: sqlite3.Row) -> SyncedEvent:
        return SyncedEvent(
            user_id=row["user_id"],
            id_appointment=row["id_appointment"],
            google_event_id=row["google_event_id"],
            calendar_id=row["calendar_id"],
            date_start=row["date_start"],
            date_end=row["date_end"],
            name=row["name"],
            etag=row["etag"],
            synced_at=row["synced_at"],
        )

    # ── google_accounts ──────────────────────────────────────────────────────

    def get_account(self, user_id: int) -> GoogleAccount | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM google_accounts WHERE user_id = ?", (user_id,)
            ).fetchone()
            return self._row_to_account(row) if row else None

    def upsert_account(
        self,
        user_id: int,
        google_email: str,
        access_token: str,
        refresh_token: str,
        token_expiry: str | None,
        scopes: str,
    ) -> GoogleAccount:
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            row = conn.execute(
                """
                INSERT INTO google_accounts
                    (user_id, google_email, access_token, refresh_token,
                     token_expiry, scopes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    google_email   = excluded.google_email,
                    access_token   = excluded.access_token,
                    refresh_token  = excluded.refresh_token,
                    token_expiry   = excluded.token_expiry,
                    scopes         = excluded.scopes
                RETURNING *
                """,
                (user_id, google_email, access_token, refresh_token, token_expiry, scopes, now),
            ).fetchone()
            conn.commit()
            return self._row_to_account(row)

    def update_calendar(
        self, user_id: int, calendar_id: str, calendar_summary: str
    ) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE google_accounts
                SET calendar_id = ?, calendar_summary = ?, sync_enabled = 1
                WHERE user_id = ?
                """,
                (calendar_id, calendar_summary, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def update_tokens(
        self, user_id: int, access_token: str, token_expiry: str | None
    ) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE google_accounts SET access_token = ?, token_expiry = ? WHERE user_id = ?",
                (access_token, token_expiry, user_id),
            )
            conn.commit()

    def update_sync_status(self, user_id: int, status: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE google_accounts
                SET last_sync_at = ?, last_sync_status = ?
                WHERE user_id = ?
                """,
                (datetime.now().isoformat(), status, user_id),
            )
            conn.commit()

    def disable_sync(self, user_id: int, reason: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE google_accounts
                SET sync_enabled = 0, last_sync_status = ?
                WHERE user_id = ?
                """,
                (reason, user_id),
            )
            conn.commit()

    def delete_account(self, user_id: int) -> None:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM google_accounts WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM synced_events WHERE user_id = ?", (user_id,))
            conn.commit()

    def get_all_sync_enabled_user_ids(self) -> list[int]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT user_id FROM google_accounts
                WHERE sync_enabled = 1 AND calendar_id IS NOT NULL
                  AND wodapp_session_enc IS NOT NULL
                """
            ).fetchall()
            return [row["user_id"] for row in rows]

    def store_wodapp_session_enc(self, user_id: int, session_enc: str) -> None:
        """Store the encrypted WodApp AuthSession JSON for background sync."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE google_accounts SET wodapp_session_enc = ? WHERE user_id = ?",
                (session_enc, user_id),
            )
            conn.commit()

    def get_wodapp_session_enc(self, user_id: int) -> str | None:
        """Retrieve the encrypted WodApp AuthSession JSON, or None if not stored."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT wodapp_session_enc FROM google_accounts WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return row["wodapp_session_enc"] if row else None

    # ── synced_events ────────────────────────────────────────────────────────

    def get_synced_events(self, user_id: int) -> list[SyncedEvent]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM synced_events WHERE user_id = ?", (user_id,)
            ).fetchall()
            return [self._row_to_event(row) for row in rows]

    def upsert_synced_event(
        self,
        user_id: int,
        id_appointment: int,
        google_event_id: str,
        calendar_id: str,
        date_start: str,
        date_end: str,
        name: str,
        etag: str | None = None,
    ) -> None:
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO synced_events
                    (user_id, id_appointment, google_event_id, calendar_id,
                     date_start, date_end, name, etag, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, id_appointment) DO UPDATE SET
                    google_event_id = excluded.google_event_id,
                    calendar_id     = excluded.calendar_id,
                    date_start      = excluded.date_start,
                    date_end        = excluded.date_end,
                    name            = excluded.name,
                    etag            = excluded.etag,
                    synced_at       = excluded.synced_at
                """,
                (
                    user_id, id_appointment, google_event_id, calendar_id,
                    date_start, date_end, name, etag, now,
                ),
            )
            conn.commit()

    def delete_synced_event(self, user_id: int, id_appointment: int) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "DELETE FROM synced_events WHERE user_id = ? AND id_appointment = ?",
                (user_id, id_appointment),
            )
            conn.commit()
