"""Google Calendar sync models."""

from pydantic import BaseModel


class GoogleAccount(BaseModel):
    """Google account linked to a WodPlanner user."""

    user_id: int
    google_email: str
    access_token: str
    refresh_token: str
    token_expiry: str | None = None
    scopes: str
    calendar_id: str | None = None
    calendar_summary: str | None = None
    sync_enabled: bool = False
    last_sync_at: str | None = None
    last_sync_status: str | None = None
    created_at: str


class SyncedEvent(BaseModel):
    """Mapping of a WodApp appointment to a Google Calendar event."""

    user_id: int
    id_appointment: int
    google_event_id: str
    calendar_id: str
    date_start: str
    date_end: str
    name: str
    etag: str | None = None
    synced_at: str
