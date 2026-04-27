"""Calendar sync engine — diff WodApp reservations against Google Calendar.

Phase 2: insert-only. Phase 3 will add update and delete.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from wodplanner.api.client import WodAppClient
from wodplanner.app.config import settings
from wodplanner.models.google import GoogleAccount
from wodplanner.services import crypto
from wodplanner.services import google_calendar as gcal
from wodplanner.services.google_accounts import GoogleAccountsService
from wodplanner.services.google_oauth import refresh_access_token

logger = logging.getLogger(__name__)

_TIMEZONE = "Europe/Amsterdam"
_DEFAULT_CLASS_DURATION = timedelta(hours=1)
_PROP_KEY = "wodplanner_appointment_id"


@dataclass
class SyncResult:
    inserted: int = 0
    updated: int = 0
    deleted: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def get_valid_token(
    account: GoogleAccount,
    db: GoogleAccountsService,
    enc_key: bytes,
) -> str:
    """Return a valid access token, refreshing via refresh_token when near expiry."""
    raw_token = crypto.decrypt(account.access_token, enc_key)

    if account.token_expiry:
        expiry = datetime.fromisoformat(account.token_expiry)
        if datetime.now() + timedelta(minutes=5) >= expiry:
            raw_refresh = crypto.decrypt(account.refresh_token, enc_key)
            new_token, new_expiry = refresh_access_token(
                raw_refresh,
                settings.google_client_id,  # type: ignore[arg-type]
                settings.google_client_secret,  # type: ignore[arg-type]
            )
            db.update_tokens(
                account.user_id,
                crypto.encrypt(new_token, enc_key),
                new_expiry,
            )
            return new_token

    return raw_token


def _build_event(
    reservation: dict,
    gym_name: str,
    first_name: str,
) -> dict:
    start: datetime = reservation["date_start"]
    end: datetime = reservation.get("date_end") or start + _DEFAULT_CLASS_DURATION
    appt_id: int = reservation["id_appointment"]
    return {
        "summary": f"{first_name} - {reservation['name']}",
        "location": gym_name,
        "start": {"dateTime": start.isoformat(), "timeZone": _TIMEZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": _TIMEZONE},
        "description": f"Class: {reservation['name']}",
        "extendedProperties": {
            "private": {_PROP_KEY: str(appt_id)}
        },
    }


def sync_user(
    account: GoogleAccount,
    db: GoogleAccountsService,
    client: WodAppClient,
    enc_key: bytes,
    first_name: str,
    gym_name: str,
) -> SyncResult:
    """Sync upcoming reservations to Google Calendar for one user.

    Phase 2: insert-only (no update/delete).
    Phase 3 will add the full diff (update + delete).
    """
    result = SyncResult()

    if not account.calendar_id:
        result.errors.append("no calendar selected")
        return result

    try:
        access_token = get_valid_token(account, db, enc_key)
    except Exception as exc:
        logger.exception("Token refresh failed for user %d", account.user_id)
        db.disable_sync(account.user_id, f"token refresh failed: {exc}")
        result.errors.append(f"token refresh failed: {exc}")
        return result

    try:
        reservations, _ = client.get_upcoming_reservations()
    except Exception as exc:
        # Never delete events when WodApp call fails.
        logger.exception("WodApp fetch failed for user %d", account.user_id)
        status = f"error: WodApp fetch failed: {exc}"
        db.update_sync_status(account.user_id, status)
        result.errors.append(status)
        return result

    existing = {ev.id_appointment: ev for ev in db.get_synced_events(account.user_id)}
    desired = {r["id_appointment"]: r for r in reservations}

    to_insert = {k: v for k, v in desired.items() if k not in existing}

    for appt_id, reservation in to_insert.items():
        try:
            event_body = _build_event(reservation, gym_name, first_name)
            created = gcal.insert_event(access_token, account.calendar_id, event_body)
            db.upsert_synced_event(
                user_id=account.user_id,
                id_appointment=appt_id,
                google_event_id=created["id"],
                calendar_id=account.calendar_id,
                date_start=reservation["date_start"].isoformat(),
                date_end=(reservation.get("date_end") or reservation["date_start"] + _DEFAULT_CLASS_DURATION).isoformat(),
                name=reservation["name"],
                etag=created.get("etag"),
            )
            result.inserted += 1
        except Exception as exc:
            logger.warning(
                "Failed to insert event %d for user %d: %s", appt_id, account.user_id, exc
            )
            result.errors.append(f"insert appt {appt_id}: {exc}")

    status = "ok" if result.ok else f"partial errors: {'; '.join(result.errors[:3])}"
    db.update_sync_status(account.user_id, status)
    return result
