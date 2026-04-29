"""Cross-reference live WodApp member lists against stored Friends."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from wodplanner.api.client import WodAppClient
from wodplanner.models.calendar import Appointment
from wodplanner.models.friends import Friend

logger = logging.getLogger(__name__)

_CONCURRENCY = 5


def find_friends_in_appointments(
    appointments: list[Appointment],
    friends: list[Friend],
    client: WodAppClient,
) -> dict[int, list[Friend] | None]:
    """Return Friends present in each Appointment, keyed by Appointment ID.

    Value is a list of matching Friends (may be empty), or None if the member
    fetch failed for that Appointment.
    """
    if not friends:
        return {}

    friend_map: dict[int, Friend] = {f.appuser_id: f for f in friends}

    def fetch(appt: Appointment) -> tuple[int, list[Friend] | None]:
        try:
            members, _ = client.get_appointment_members(
                appt.id_appointment,
                appt.date_start,
                appt.date_end,
                expected_total=appt.total_subscriptions,
            )
            return appt.id_appointment, [
                friend_map[m.id_appuser]
                for m in members
                if m.id_appuser in friend_map
            ]
        except Exception as exc:
            logger.warning(
                "Failed to fetch members for appointment %s: %s",
                appt.id_appointment,
                exc,
            )
            return appt.id_appointment, None

    result: dict[int, list[Friend] | None] = {}
    with ThreadPoolExecutor(max_workers=_CONCURRENCY) as pool:
        futures = {pool.submit(fetch, appt): appt for appt in appointments}
        for future in as_completed(futures):
            appt_id, presence = future.result()
            result[appt_id] = presence

    return result
