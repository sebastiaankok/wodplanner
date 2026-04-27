"""Calendar sync engine — diff WodApp reservations against Google Calendar.

Sync phases:
  Phase 2 (insert-only): shipped
  Phase 3 (full diff): this file — insert + update + delete + recovery
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from wodplanner.api.client import WodAppClient
from wodplanner.app.config import settings
from wodplanner.models.google import GoogleAccount, SyncedEvent
from wodplanner.services import crypto
from wodplanner.services import google_calendar as gcal
from wodplanner.services.google_accounts import GoogleAccountsService
from wodplanner.services.google_oauth import refresh_access_token

logger = logging.getLogger(__name__)

_TIMEZONE = "Europe/Amsterdam"
_DEFAULT_CLASS_DURATION = timedelta(hours=1)
_PROP_KEY = "wodplanner_appointment_id"
_RECOVERY_WINDOW_DAYS = 60


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


def _build_event(reservation: dict, gym_name: str, first_name: str) -> dict:
    start: datetime = reservation["date_start"]
    end: datetime = reservation.get("date_end") or start + _DEFAULT_CLASS_DURATION
    appt_id: int = reservation["id_appointment"]
    return {
        "summary": f"{first_name} - {reservation['name']}",
        "location": gym_name,
        "start": {"dateTime": start.isoformat(), "timeZone": _TIMEZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": _TIMEZONE},
        "description": f"Class: {reservation['name']}",
        "extendedProperties": {"private": {_PROP_KEY: str(appt_id)}},
    }


def _rebuild_from_google(
    access_token: str,
    account: GoogleAccount,
    db: GoogleAccountsService,
) -> dict[int, SyncedEvent]:
    """Rebuild synced_events from Google Calendar when the DB mapping is missing.

    Queries the calendar for events tagged with wodplanner_appointment_id and
    repopulates synced_events so subsequent syncs don't duplicate-insert.
    """
    if not account.calendar_id:
        return {}
    try:
        now = datetime.now()
        events = gcal.list_events_in_range(
            access_token,
            account.calendar_id,
            time_min=now.isoformat() + "Z",
            time_max=(now + timedelta(days=_RECOVERY_WINDOW_DAYS)).isoformat() + "Z",
        )
    except Exception:
        logger.exception(
            "Recovery: failed to list events for user %d", account.user_id
        )
        return {}

    rebuilt: dict[int, SyncedEvent] = {}
    for ev in events:
        props = ev.get("extendedProperties", {}).get("private", {})
        appt_id_str = props.get(_PROP_KEY)
        if not appt_id_str or not appt_id_str.isdigit():
            continue
        appt_id = int(appt_id_str)
        date_start = ev.get("start", {}).get("dateTime", "")
        date_end = ev.get("end", {}).get("dateTime", "")
        db.upsert_synced_event(
            user_id=account.user_id,
            id_appointment=appt_id,
            google_event_id=ev["id"],
            calendar_id=account.calendar_id,
            date_start=date_start,
            date_end=date_end,
            name=ev.get("summary", ""),
            etag=ev.get("etag"),
        )
        rebuilt[appt_id] = SyncedEvent(
            user_id=account.user_id,
            id_appointment=appt_id,
            google_event_id=ev["id"],
            calendar_id=account.calendar_id,
            date_start=date_start,
            date_end=date_end,
            name=ev.get("summary", ""),
            etag=ev.get("etag"),
            synced_at=datetime.now().isoformat(),
        )
    if rebuilt:
        logger.info(
            "Recovery: rebuilt %d synced_events for user %d from Google Calendar",
            len(rebuilt),
            account.user_id,
        )
    return rebuilt


def sync_user(
    account: GoogleAccount,
    db: GoogleAccountsService,
    client: WodAppClient,
    enc_key: bytes,
    first_name: str,
    gym_name: str,
) -> SyncResult:
    """Full diff sync: insert new signups, update changed events, delete cancellations."""
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

    # Never delete events when WodApp call fails — abort and leave existing events.
    try:
        reservations, _ = client.get_upcoming_reservations()
    except Exception as exc:
        logger.exception("WodApp fetch failed for user %d", account.user_id)
        status = f"error: WodApp fetch failed: {exc}"
        db.update_sync_status(account.user_id, status)
        result.errors.append(status)
        return result

    existing = {ev.id_appointment: ev for ev in db.get_synced_events(account.user_id)}
    desired = {r["id_appointment"]: r for r in reservations}

    # Recovery: rebuild mapping from Google Calendar if DB is empty but user has signups.
    if not existing and desired:
        existing = _rebuild_from_google(access_token, account, db)

    now = datetime.now()

    # ── Insert ────────────────────────────────────────────────────────────────
    for appt_id, reservation in desired.items():
        if appt_id in existing:
            continue
        try:
            event_body = _build_event(reservation, gym_name, first_name)
            created = gcal.insert_event(access_token, account.calendar_id, event_body)
            db.upsert_synced_event(
                user_id=account.user_id,
                id_appointment=appt_id,
                google_event_id=created["id"],
                calendar_id=account.calendar_id,
                date_start=reservation["date_start"].isoformat(),
                date_end=(
                    reservation.get("date_end") or reservation["date_start"] + _DEFAULT_CLASS_DURATION
                ).isoformat(),
                name=reservation["name"],
                etag=created.get("etag"),
            )
            result.inserted += 1
        except Exception as exc:
            logger.warning(
                "Insert failed appt %d user %d: %s", appt_id, account.user_id, exc
            )
            result.errors.append(f"insert appt {appt_id}: {exc}")

    # ── Update ────────────────────────────────────────────────────────────────
    for appt_id, reservation in desired.items():
        if appt_id not in existing:
            continue
        ev = existing[appt_id]
        new_start = reservation["date_start"].isoformat()
        if ev.date_start == new_start and ev.name == reservation["name"]:
            continue
        try:
            event_body = _build_event(reservation, gym_name, first_name)
            gcal.update_event(
                access_token, account.calendar_id, ev.google_event_id, event_body
            )
            db.upsert_synced_event(
                user_id=account.user_id,
                id_appointment=appt_id,
                google_event_id=ev.google_event_id,
                calendar_id=account.calendar_id,
                date_start=new_start,
                date_end=(
                    reservation.get("date_end") or reservation["date_start"] + _DEFAULT_CLASS_DURATION
                ).isoformat(),
                name=reservation["name"],
                etag=ev.etag,
            )
            result.updated += 1
        except Exception as exc:
            logger.warning(
                "Update failed appt %d user %d: %s", appt_id, account.user_id, exc
            )
            result.errors.append(f"update appt {appt_id}: {exc}")

    # ── Delete ────────────────────────────────────────────────────────────────
    # Only delete future events — leave past events as calendar history.
    for appt_id, ev in existing.items():
        if appt_id in desired:
            continue
        try:
            event_start = datetime.fromisoformat(ev.date_start)
        except ValueError:
            continue
        if event_start <= now:
            # Class already started/finished — keep event for history.
            continue
        try:
            gcal.delete_event(access_token, account.calendar_id, ev.google_event_id)
            db.delete_synced_event(account.user_id, appt_id)
            result.deleted += 1
        except Exception as exc:
            logger.warning(
                "Delete failed appt %d user %d: %s", appt_id, account.user_id, exc
            )
            result.errors.append(f"delete appt {appt_id}: {exc}")

    status = "ok" if result.ok else f"partial errors: {'; '.join(result.errors[:3])}"
    db.update_sync_status(account.user_id, status)
    return result
