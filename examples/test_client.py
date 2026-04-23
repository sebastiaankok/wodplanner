#!/usr/bin/env python3
"""Test script to verify the WodApp API client works."""

import os
from datetime import date

from wodplanner.api import WodAppClient


def main() -> None:
    # Get credentials from environment
    username = os.environ.get("WODAPP_USERNAME")
    password = os.environ.get("WODAPP_PASSWORD")

    if not username or not password:
        print("Please set WODAPP_USERNAME and WODAPP_PASSWORD environment variables")
        print("Example:")
        print("  export WODAPP_USERNAME='your@email.com'")
        print("  export WODAPP_PASSWORD='yourpassword'")
        return

    with WodAppClient() as client:
        # Login
        print("Logging in...")
        session = client.login(username, password)
        print(f"Logged in as {session.firstname} ({session.username})")
        print(f"Gym: {session.gym_name} (ID: {session.gym_id})")
        print(f"Agenda ID: {session.agenda_id}")
        print()

        # Get today's schedule
        print(f"Schedule for today ({date.today()}):")
        print("-" * 60)
        appointments = client.get_day_schedule()

        for appt in appointments:
            status_icon = {
                "open": " ",
                "closed": "X",
                "subscribed": "*",
            }.get(appt.status, "?")

            print(
                f"[{status_icon}] {appt.date_start.strftime('%H:%M')}-{appt.date_end.strftime('%H:%M')} "
                f"{appt.name:20} ({appt.total_subscriptions}/{appt.max_subscriptions})"
            )

        print()
        print("Legend: [ ] = open, [X] = full, [*] = subscribed")
        print()

        # Get details of the first appointment with people
        if appointments:
            appt = appointments[0]
            print(f"Details for '{appt.name}' at {appt.date_start.strftime('%H:%M')}:")
            print("-" * 60)

            details = client.get_appointment_details(
                appt.id_appointment,
                appt.date_start,
                appt.date_end,
            )

            print(f"Signup opens: {details.subscription_open_date}")
            print(f"Open for signup: {details.is_open_for_signup()}")
            print(f"Spots available: {details.has_spots_available()}")
            print(f"Waiting list enabled: {bool(details.waiting_list)}")
            print()

            if details.subscriptions.members:
                print("Signed up members:")
                for member in details.subscriptions.members:
                    print(f"  - {member.name} (ID: {member.id_appuser})")


if __name__ == "__main__":
    main()
