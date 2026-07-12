"""CLI tool to seed subscription_events with realistic test data for development.

Usage:
    seed-subscriptions --user-id 123 --dry-run
    seed-subscriptions --user-id 123 --weeks 26 --avg-per-week 4
    seed-subscriptions --user-id 123 --db-path /tmp/test.db
"""

import argparse
import os
import random
from datetime import date, datetime, timedelta
from pathlib import Path

from wodplanner.services.subscription_tracker import SubscriptionTrackerService

CLASS_NAMES = [
    "CrossFit", "CrossFit", "CrossFit", "CrossFit",
    "Olympic Lifting", "Gymnastics",
]


def generate_events(
    user_id: int,
    weeks: int,
    avg_per_week: int,
    dry_run: bool,
    db_path: Path,
) -> None:
    svc = SubscriptionTrackerService(db_path) if not dry_run else None
    today = date.today()
    total = 0
    next_appt_id = 900000

    print(
        f"Simulating {weeks} weeks of sessions for user {user_id} "
        f"(avg {avg_per_week}/week, dry_run={dry_run})"
    )

    for week_offset in range(weeks, 0, -1):
        monday = today - timedelta(weeks=week_offset)
        count = max(1, avg_per_week + random.randint(-1, 1))
        days = sorted(random.sample(range(5), count))

        session_days = []
        for dow in days:
            class_date = monday + timedelta(days=dow)
            class_name = random.choice(CLASS_NAMES)
            hour = random.choice([7, 8, 9, 12, 17, 18, 19])
            class_start = datetime(
                class_date.year, class_date.month, class_date.day, hour, 0
            )
            class_end = class_start + timedelta(hours=1)
            if not dry_run:
                svc.record_subscribe(
                    user_id=user_id,
                    appointment_id=next_appt_id,
                    class_name=class_name,
                    class_date=class_date,
                    class_end=class_end,
                )
            session_days.append(f"{class_date.strftime('%a')} {class_name}")
            next_appt_id += 1
            total += 1

        print(
            f"  Week {monday.isoformat()}: {len(days)} sessions"
            f" — {', '.join(session_days)}"
        )

    if dry_run:
        print(f"\nTotal: {total} events (DRY RUN — no changes made)")
    else:
        print(f"\nTotal: {total} events inserted")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed test subscription events for the weekly chart"
    )
    parser.add_argument("--user-id", type=int, required=True, help="WodApp user ID")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path(os.environ.get("DB_PATH", "/data/wodplanner.db")),
        help="Path to SQLite database (default: $DB_PATH env var or /data/wodplanner.db)",
    )
    parser.add_argument(
        "--weeks",
        type=int,
        default=12,
        help="Number of weeks to go back and fill (default: 12)",
    )
    parser.add_argument(
        "--avg-per-week",
        type=int,
        default=3,
        help="Average sessions per week (default: 3, varies ±1)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview events without inserting",
    )
    args = parser.parse_args()

    generate_events(
        user_id=args.user_id,
        weeks=args.weeks,
        avg_per_week=args.avg_per_week,
        dry_run=args.dry_run,
        db_path=args.db_path,
    )


if __name__ == "__main__":
    main()