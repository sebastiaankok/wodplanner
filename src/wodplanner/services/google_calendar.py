"""Thin Google Calendar API v3 wrapper using httpx."""

import httpx

_BASE = "https://www.googleapis.com/calendar/v3"
_TIMEOUT = 15


def _auth_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def list_calendars(access_token: str) -> list[dict]:
    resp = httpx.get(
        f"{_BASE}/users/me/calendarList",
        headers=_auth_headers(access_token),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("items", [])


def create_calendar(access_token: str, summary: str) -> dict:
    """Create a new calendar. Returns the calendar resource."""
    resp = httpx.post(
        f"{_BASE}/calendars",
        headers=_auth_headers(access_token),
        json={"summary": summary},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def insert_event(access_token: str, calendar_id: str, event: dict) -> dict:
    """Insert a calendar event. Returns the created event resource."""
    resp = httpx.post(
        f"{_BASE}/calendars/{calendar_id}/events",
        headers=_auth_headers(access_token),
        json=event,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def update_event(
    access_token: str, calendar_id: str, event_id: str, event: dict
) -> dict:
    """Full-replace update of a calendar event."""
    resp = httpx.put(
        f"{_BASE}/calendars/{calendar_id}/events/{event_id}",
        headers=_auth_headers(access_token),
        json=event,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def delete_event(access_token: str, calendar_id: str, event_id: str) -> None:
    """Delete a calendar event. 404 is silently ignored."""
    resp = httpx.delete(
        f"{_BASE}/calendars/{calendar_id}/events/{event_id}",
        headers=_auth_headers(access_token),
        timeout=_TIMEOUT,
    )
    if resp.status_code != 404:
        resp.raise_for_status()


def list_events_with_private_property(
    access_token: str, calendar_id: str, prop_key: str, prop_value: str
) -> list[dict]:
    """List events that have a specific private extended property set."""
    resp = httpx.get(
        f"{_BASE}/calendars/{calendar_id}/events",
        headers=_auth_headers(access_token),
        params={"privateExtendedProperty": f"{prop_key}={prop_value}"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("items", [])
