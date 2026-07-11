"""SubscriptionTrackerService — log subscribe/unsubscribe events for weekly session tracking."""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime, timedelta

from wodplanner.services import migrations
from wodplanner.services.base import BaseService

logger = logging.getLogger(__name__)


def _migrate_v700(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS subscription_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            appointment_id INTEGER NOT NULL,
            class_name TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK(event_type IN ('subscribe', 'unsubscribe')),
            class_date TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sub_events_user_date ON subscription_events(user_id, class_date)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sub_events_user_appt ON subscription_events(user_id, appointment_id)"
    )


def _migrate_v701(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE subscription_events ADD COLUMN class_end TEXT")


migrations.register(
    700,
    "Create subscription_events table for weekly session tracking",
    _migrate_v700,
)

migrations.register(
    701,
    "Add class_end column to subscription_events for time-based past/future classification",
    _migrate_v701,
)

class SubscriptionTrackerService(BaseService):
    def record_subscribe(
        self, user_id: int, appointment_id: int, class_name: str, class_date: date,
        class_end: datetime | None = None,
    ) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO subscription_events (user_id, appointment_id, class_name, event_type, class_date, class_end, created_at)
                VALUES (?, ?, ?, 'subscribe', ?, ?, ?)
                """,
                (user_id, appointment_id, class_name, class_date.isoformat(),
                 class_end.isoformat() if class_end else None, datetime.now().isoformat()),
            )

    def record_unsubscribe(
        self, user_id: int, appointment_id: int, class_name: str, class_date: date,
        class_end: datetime | None = None,
    ) -> None:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT SUM(CASE WHEN event_type = 'subscribe' THEN 1 ELSE -1 END) AS net
                FROM subscription_events
                WHERE user_id = ? AND appointment_id = ?
                """,
                (user_id, appointment_id),
            ).fetchone()
            current_net = row["net"] if row and row["net"] is not None else 0
            if current_net <= 0:
                return
            conn.execute(
                """
                INSERT INTO subscription_events (user_id, appointment_id, class_name, event_type, class_date, class_end, created_at)
                VALUES (?, ?, ?, 'unsubscribe', ?, ?, ?)
                """,
                (user_id, appointment_id, class_name, class_date.isoformat(),
                 class_end.isoformat() if class_end else None, datetime.now().isoformat()),
            )

    def get_weekly_counts(
        self, user_id: int, weeks: int = 52
    ) -> list[dict]:
        """Return list of {week_start, past_count, future_count} for last N weeks."""
        now = datetime.now()
        today = date.today()
        # Start of current week (Monday)
        current_monday = today - timedelta(days=today.weekday())
        # Go back N weeks from Monday after current week so we get full weeks
        start = current_monday - timedelta(weeks=weeks)

        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    class_date,
                    class_end,
                    SUM(CASE WHEN event_type = 'subscribe' THEN 1 ELSE -1 END) AS net
                FROM subscription_events
                WHERE user_id = ?
                  AND class_date >= ?
                GROUP BY appointment_id
                HAVING net > 0
                """,
                (user_id, start.isoformat()),
            ).fetchall()

        # Group by week, split past vs future
        weeks_data: dict[str, dict] = {}
        for row in rows:
            d = date.fromisoformat(row["class_date"])
            week_monday = d - timedelta(days=d.weekday())
            key = week_monday.isoformat()
            if key not in weeks_data:
                weeks_data[key] = {"past": 0, "future": 0}
            if row["class_end"]:
                class_end = datetime.fromisoformat(row["class_end"])
                if class_end < now:
                    weeks_data[key]["past"] += row["net"]
                else:
                    weeks_data[key]["future"] += row["net"]
            else:
                if d < today:
                    weeks_data[key]["past"] += row["net"]
                else:
                    weeks_data[key]["future"] += row["net"]

        # Build complete list of 52 weeks
        result = []
        for i in range(weeks):
            monday = current_monday + timedelta(weeks=i - weeks + 1)
            key = monday.isoformat()
            entry = weeks_data.get(key, {"past": 0, "future": 0})
            entry["week_start"] = key
            result.append(entry)

        return result

    def get_current_week_stats(self, user_id: int) -> dict:
        """Return {past, future} for current week."""
        now = datetime.now()
        current_monday = date.today() - timedelta(days=date.today().weekday())
        return self._get_week_stats(user_id, current_monday, now)

    def _get_week_stats(self, user_id: int, week_monday: date, now: datetime | None = None) -> dict:
        today = date.today()
        now = now or datetime.now()
        week_end = week_monday + timedelta(days=7)
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    class_date,
                    class_end,
                    SUM(CASE WHEN event_type = 'subscribe' THEN 1 ELSE -1 END) AS net
                FROM subscription_events
                WHERE user_id = ?
                  AND class_date >= ?
                  AND class_date < ?
                GROUP BY appointment_id
                HAVING net > 0
                """,
                (user_id, week_monday.isoformat(), week_end.isoformat()),
            ).fetchall()

        past = 0
        future = 0
        for row in rows:
            d = date.fromisoformat(row["class_date"])
            if row["class_end"]:
                class_end = datetime.fromisoformat(row["class_end"])
                if class_end < now:
                    past += row["net"]
                else:
                    future += row["net"]
            else:
                if d < today:
                    past += row["net"]
                else:
                    future += row["net"]
        return {"past": past, "future": future}

    def get_average_per_week(self, user_id: int) -> float:
        """Average past sessions per complete week."""
        today = date.today()
        current_monday = today - timedelta(days=today.weekday())

        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    class_date,
                    SUM(CASE WHEN event_type = 'subscribe' THEN 1 ELSE -1 END) AS net
                FROM subscription_events
                WHERE user_id = ?
                  AND class_date < ?
                GROUP BY appointment_id
                HAVING net > 0
                """,
                (user_id, current_monday.isoformat()),
            ).fetchall()

        if not rows:
            return 0.0

        # Group into weeks
        week_counts: dict[str, int] = {}
        for row in rows:
            d = date.fromisoformat(row["class_date"])
            week_key = (d - timedelta(days=d.weekday())).isoformat()
            week_counts[week_key] = week_counts.get(week_key, 0) + row["net"]

        if not week_counts:
            return 0.0

        return sum(week_counts.values()) / len(week_counts)

    def has_any_events(self, user_id: int) -> bool:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM subscription_events WHERE user_id = ? LIMIT 1",
                (user_id,),
            ).fetchone()
            return row is not None

    def get_weeks_tracked(self, user_id: int) -> int:
        """Number of distinct weeks with past sessions."""
        today = date.today()
        current_monday = today - timedelta(days=today.weekday())
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT
                    CAST(JULIANDAY(class_date) - JULIANDAY('2000-01-03') AS INTEGER) / 7 AS week_num
                FROM subscription_events
                WHERE user_id = ?
                  AND class_date < ?
                """,
                (user_id, current_monday.isoformat()),
            ).fetchall()
            return len(rows)