"""Friends service for managing friend list."""

import sqlite3
from datetime import datetime
from typing import cast

from wodplanner.models.friends import Friend
from wodplanner.models.user import User
from wodplanner.services import migrations
from wodplanner.services.base import BaseService
from wodplanner.utils.dates import parse_iso_datetime


def _migrate_v200(conn: sqlite3.Connection) -> None:
    """Create friends table; migrate old single-column UNIQUE(appuser_id) schema."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS friends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_user_id INTEGER NOT NULL DEFAULT 0,
            appuser_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            added_at TEXT NOT NULL,
            UNIQUE(owner_user_id, appuser_id)
        )
        """
    )
    table_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='friends'"
    ).fetchone()[0]
    needs_migration = (
        "owner_user_id" not in table_sql or "UNIQUE(owner_user_id" not in table_sql
    )
    if needs_migration:
        conn.execute("ALTER TABLE friends RENAME TO friends_old")
        conn.execute(
            """
            CREATE TABLE friends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_user_id INTEGER NOT NULL DEFAULT 0,
                appuser_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                added_at TEXT NOT NULL,
                UNIQUE(owner_user_id, appuser_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO friends (id, owner_user_id, appuser_id, name, added_at)
            SELECT id, 0, appuser_id, name, added_at FROM friends_old
            """
        )
        conn.execute("DROP TABLE friends_old")


migrations.register(200, "create friends table (owner-scoped)", _migrate_v200)


def _migrate_v803(conn: sqlite3.Connection) -> None:
    """Recreate friends with FK to users + soft-delete + index."""
    if migrations.has_fk_to(conn, "friends", "users") and migrations.has_column(
        conn, "friends", "deleted_at"
    ):
        return
    with migrations.fk_disabled(conn):
        conn.execute("ALTER TABLE friends RENAME TO friends_old")
        conn.execute(
            """
            CREATE TABLE friends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                appuser_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                added_at TEXT NOT NULL,
                deleted_at TEXT,
                UNIQUE(owner_user_id, appuser_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO friends (id, owner_user_id, appuser_id, name, added_at, deleted_at)
            SELECT id, owner_user_id, appuser_id, name, added_at, NULL FROM friends_old
            """
        )
        conn.execute("DROP TABLE friends_old")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_friends_owner ON friends(owner_user_id)")


migrations.register(803, "recreate friends with FK users + soft-delete", _migrate_v803)


def _migrate_v210(conn: sqlite3.Connection) -> None:
    """Create data_shares table for bidirectional data sharing."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS data_shares (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id_a INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            user_id_b INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            requested_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'accepted', 'declined')),
            created_at TEXT NOT NULL,
            updated_at TEXT,
            deleted_at TEXT,
            UNIQUE(user_id_a, user_id_b),
            CHECK(user_id_a < user_id_b),
            CHECK(requested_by IN (user_id_a, user_id_b))
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_data_shares_a ON data_shares(user_id_a)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_data_shares_b ON data_shares(user_id_b)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_data_shares_status ON data_shares(status)")


migrations.register(210, "create data_shares table", _migrate_v210)


class DataShareService(BaseService):
    """Service for managing bidirectional data sharing between users."""

    def _get_partner_id(self, user_id: int, row: sqlite3.Row) -> int:
        return cast(int, row["user_id_b"] if row["user_id_a"] == user_id else row["user_id_a"])

    def send_request(self, from_user_id: int, to_user_id: int) -> bool:
        """Send a data sharing request. Returns False if already exists."""
        if from_user_id == to_user_id:
            return False
        user_id_a, user_id_b = (from_user_id, to_user_id) if from_user_id < to_user_id else (to_user_id, from_user_id)
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            existing = conn.execute(
                "SELECT id, status, deleted_at FROM data_shares WHERE user_id_a = ? AND user_id_b = ?",
                (user_id_a, user_id_b),
            ).fetchone()
            if existing and existing["status"] == "accepted" and existing["deleted_at"] is None:
                return False
            if existing:
                conn.execute(
                    "UPDATE data_shares SET status = 'pending', requested_by = ?, updated_at = ?, deleted_at = NULL WHERE id = ?",
                    (from_user_id, now, existing["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO data_shares (user_id_a, user_id_b, requested_by, status, created_at, updated_at)
                    VALUES (?, ?, ?, 'pending', ?, ?)
                    """,
                    (user_id_a, user_id_b, from_user_id, now, now),
                )
            conn.commit()
            return True

    def accept_request(self, user_id: int, requester_id: int) -> bool:
        """Accept an incoming data sharing request."""
        user_id_a, user_id_b = (user_id, requester_id) if user_id < requester_id else (requester_id, user_id)
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE data_shares SET status = 'accepted', updated_at = ? WHERE user_id_a = ? AND user_id_b = ? AND status = 'pending' AND deleted_at IS NULL",
                (datetime.now().isoformat(), user_id_a, user_id_b),
            )
            conn.commit()
            return cursor.rowcount > 0

    def decline_request(self, user_id: int, requester_id: int) -> bool:
        """Decline an incoming data sharing request."""
        user_id_a, user_id_b = (user_id, requester_id) if user_id < requester_id else (requester_id, user_id)
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE data_shares SET status = 'declined', updated_at = ? WHERE user_id_a = ? AND user_id_b = ? AND status = 'pending' AND deleted_at IS NULL",
                (datetime.now().isoformat(), user_id_a, user_id_b),
            )
            conn.commit()
            return cursor.rowcount > 0

    def cancel_request(self, user_id: int, to_user_id: int) -> bool:
        """Cancel an outgoing pending request. Hard-deletes so user can re-send."""
        user_id_a, user_id_b = (user_id, to_user_id) if user_id < to_user_id else (to_user_id, user_id)
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM data_shares WHERE user_id_a = ? AND user_id_b = ? AND status = 'pending' AND requested_by = ?",
                (user_id_a, user_id_b, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def revoke_share(self, user_id: int, partner_id: int) -> bool:
        """Revoke an accepted share (either party)."""
        user_id_a, user_id_b = (user_id, partner_id) if user_id < partner_id else (partner_id, user_id)
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE data_shares SET deleted_at = ?, updated_at = ? WHERE user_id_a = ? AND user_id_b = ? AND status = 'accepted' AND deleted_at IS NULL",
                (datetime.now().isoformat(), datetime.now().isoformat(), user_id_a, user_id_b),
            )
            conn.commit()
            return cursor.rowcount > 0

    def _get_share_row(self, user_id: int, other_user_id: int) -> sqlite3.Row | None:
        user_id_a, user_id_b = (user_id, other_user_id) if user_id < other_user_id else (other_user_id, user_id)
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM data_shares WHERE user_id_a = ? AND user_id_b = ? AND deleted_at IS NULL",
                (user_id_a, user_id_b),
            ).fetchone()
            return cast(sqlite3.Row | None, row)

    def get_share_status(self, user_id: int, other_user_id: int) -> str | None:
        """Get share status: None, 'pending_outgoing', 'pending_incoming', 'accepted'."""
        row = self._get_share_row(user_id, other_user_id)
        if not row:
            return None
        if row["status"] == "accepted":
            return "accepted"
        if row["status"] == "pending":
            return "pending_outgoing" if row["requested_by"] == user_id else "pending_incoming"
        return None

    def get_incoming_requests(self, user_id: int) -> list[int]:
        """Get list of user IDs who have sent pending requests to this user."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT user_id_a, user_id_b FROM data_shares WHERE (user_id_a = ? OR user_id_b = ?) AND status = 'pending' AND requested_by != ? AND deleted_at IS NULL",
                (user_id, user_id, user_id),
            ).fetchall()
            return [self._get_partner_id(user_id, row) for row in rows]

    def get_outgoing_requests(self, user_id: int) -> list[int]:
        """Get list of user IDs that this user has pending requests to."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT user_id_a, user_id_b FROM data_shares WHERE (user_id_a = ? OR user_id_b = ?) AND status = 'pending' AND requested_by = ? AND deleted_at IS NULL",
                (user_id, user_id, user_id),
            ).fetchall()
            return [self._get_partner_id(user_id, row) for row in rows]

    def get_partners(self, user_id: int) -> list[int]:
        """Get list of user IDs this user has an accepted share with."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT user_id_a, user_id_b FROM data_shares WHERE (user_id_a = ? OR user_id_b = ?) AND status = 'accepted' AND deleted_at IS NULL",
                (user_id, user_id),
            ).fetchall()
            return [self._get_partner_id(user_id, row) for row in rows]

    def get_partner_users(self, user_id: int, user_service=None) -> list[User]:
        """Get User models for all data sharing partners."""
        partner_ids = self.get_partners(user_id)
        if not partner_ids or not user_service:
            return []
        users = []
        for pid in partner_ids:
            u = user_service.get(pid)
            if u:
                users.append(u)
        return users

    def get_incoming_request_count(self, user_id: int) -> int:
        """Count pending incoming requests."""
        return len(self.get_incoming_requests(user_id))

    def get_local_user_id(self, appuser_id: int) -> int | None:
        """Resolve a WodApp appuser_id to local users.id."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE appuser_id = ?", (appuser_id,)
            ).fetchone()
            return row[0] if row else None

    def get_display_name(self, user_id: int) -> str | None:
        """Get display_name for a local user."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT display_name FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            return row[0] if row else None

    def get_share_statuses_for_friends(self, user_id: int, friend_appuser_ids: list[int]) -> dict[int, str | None]:
        """Get share status keyed by friend appuser_id for the friends list view."""
        result: dict[int, str | None] = {}
        for aid in friend_appuser_ids:
            local_id = self.get_local_user_id(aid)
            if local_id:
                result[aid] = self.get_share_status(user_id, local_id)
            else:
                result[aid] = None
        return result


class FriendsService(BaseService):
    """Service for managing friends with SQLite storage."""

    def _row_to_model(self, row: sqlite3.Row) -> Friend:
        return Friend(
            id=row["id"],
            owner_user_id=row["owner_user_id"],
            appuser_id=row["appuser_id"],
            name=row["name"],
            added_at=parse_iso_datetime(row["added_at"]),
        )

    def add(self, owner_user_id: int, appuser_id: int, name: str) -> Friend:
        """Add a friend for the given owner."""
        with self._get_connection() as conn:
            row = conn.execute(
                """
                INSERT INTO friends (owner_user_id, appuser_id, name, added_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(owner_user_id, appuser_id) DO UPDATE SET name = excluded.name
                RETURNING *
                """,
                (owner_user_id, appuser_id, name, datetime.now().isoformat()),
            ).fetchone()
            conn.commit()
            return self._row_to_model(row)

    def get(self, owner_user_id: int, friend_id: int) -> Friend | None:
        """Get a friend by ID, scoped to owner."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM friends WHERE id = ? AND owner_user_id = ? AND deleted_at IS NULL",
                (friend_id, owner_user_id),
            ).fetchone()
            return self._row_to_model(row) if row else None

    def get_by_appuser_id(self, owner_user_id: int, appuser_id: int) -> Friend | None:
        """Get a friend by WodApp user ID, scoped to owner."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM friends WHERE owner_user_id = ? AND appuser_id = ? AND deleted_at IS NULL",
                (owner_user_id, appuser_id),
            ).fetchone()
            return self._row_to_model(row) if row else None

    def get_all(self, owner_user_id: int) -> list[Friend]:
        """Get all friends for owner."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM friends WHERE owner_user_id = ? AND deleted_at IS NULL ORDER BY name",
                (owner_user_id,),
            ).fetchall()
            return [self._row_to_model(row) for row in rows]

    def get_appuser_ids(self, owner_user_id: int) -> set[int]:
        """Get set of friend appuser IDs for quick lookup, scoped to owner."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT appuser_id FROM friends WHERE owner_user_id = ? AND deleted_at IS NULL",
                (owner_user_id,),
            ).fetchall()
            return {row["appuser_id"] for row in rows}

    def delete(self, owner_user_id: int, friend_id: int) -> bool:
        """Soft-delete a friend by ID, scoped to owner."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE friends SET deleted_at = ? WHERE id = ? AND owner_user_id = ? AND deleted_at IS NULL",
                (datetime.now().isoformat(), friend_id, owner_user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_by_appuser_id(self, owner_user_id: int, appuser_id: int) -> bool:
        """Soft-delete a friend by WodApp user ID, scoped to owner."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE friends SET deleted_at = ? WHERE owner_user_id = ? AND appuser_id = ? AND deleted_at IS NULL",
                (datetime.now().isoformat(), owner_user_id, appuser_id),
            )
            conn.commit()
            return cursor.rowcount > 0
