"""FastAPI dependencies for dependency injection."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, Response, status

from wodplanner.api.client import WodAppClient
from wodplanner.app.config import settings
from wodplanner.models.auth import AuthSession
from wodplanner.services import crypto
from wodplanner.services import session as cookie_session
from wodplanner.services.api_cache import ApiCacheService
from wodplanner.services.calendar_sync import CalendarSyncService
from wodplanner.services.friends import FriendsService
from wodplanner.services.google_accounts import GoogleAccountsService
from wodplanner.services.one_rep_max import OneRepMaxService
from wodplanner.services.preferences import PreferencesService
from wodplanner.services.schedule import ScheduleService
from wodplanner.services.subscription import SubscriptionService


def _get_db_path() -> Path:
    return Path(os.environ.get("DB_PATH", "/data/wodplanner.db"))


@lru_cache
def get_friends_service() -> FriendsService:
    """Get the singleton friends service."""
    return FriendsService(_get_db_path())


@lru_cache
def get_preferences_service() -> PreferencesService:
    """Get the singleton preferences service."""
    return PreferencesService(_get_db_path())


@lru_cache
def get_schedule_service() -> ScheduleService:
    """Get the singleton schedule service."""
    return ScheduleService(_get_db_path())


@lru_cache
def get_one_rep_max_service() -> OneRepMaxService:
    """Get the singleton one rep max service."""
    return OneRepMaxService(_get_db_path())


@lru_cache
def get_google_accounts_service() -> GoogleAccountsService:
    """Get the singleton Google accounts service."""
    enc_key = crypto.get_enc_key(settings.google_token_enc_key, settings.secret_key)
    return GoogleAccountsService(_get_db_path(), enc_key)


@lru_cache
def get_calendar_sync_service() -> CalendarSyncService:
    """Get the singleton calendar sync service."""
    return CalendarSyncService(
        db=get_google_accounts_service(),
        schedule_service=get_schedule_service(),
    )


@lru_cache
def get_api_cache_service() -> ApiCacheService:
    """Get the singleton API cache service."""
    return ApiCacheService(ttl_seconds=settings.api_cache_ttl_seconds)


def get_session_from_cookie(
    session: Annotated[str | None, Cookie()] = None,
) -> AuthSession | None:
    """
    Get AuthSession from cookie if present and valid.

    Returns None if no session cookie or session is expired/invalid.
    """
    if not session:
        return None
    max_age = settings.session_expire_days * 24 * 60 * 60 if settings.session_expire_days else None
    return cookie_session.decode(session, settings.secret_key, max_age)


def require_session(
    session: Annotated[AuthSession | None, Depends(get_session_from_cookie)],
) -> AuthSession:
    """
    Require a valid session for API routes.

    Raises 401 Unauthorized if no valid session.
    """
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return session


def require_session_for_view(
    request: Request,
    session: Annotated[AuthSession | None, Depends(get_session_from_cookie)],
) -> AuthSession:
    """
    Require a valid session for HTML view routes.

    Redirects to /login if no valid session.
    For HTMX requests, returns HX-Redirect header.
    """
    if session is None:
        # Check if this is an HTMX request
        if request.headers.get("HX-Request"):
            # Return a response that triggers client-side redirect
            response = Response(status_code=200)
            response.headers["HX-Redirect"] = "/login"
            raise HTTPException(
                status_code=status.HTTP_200_OK,
                headers={"HX-Redirect": "/login"},
            )
        # Regular request - redirect
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )
    return session


def get_client_from_session(
    session: Annotated[AuthSession, Depends(require_session)],
) -> WodAppClient:
    """
    Create a WodAppClient from the authenticated session.

    This creates a new client per request using stored session data.
    """
    return WodAppClient.from_session(session, cache=get_api_cache_service())


def get_client_from_session_for_view(
    session: Annotated[AuthSession, Depends(require_session_for_view)],
) -> WodAppClient:
    """
    Create a WodAppClient from session for view routes.

    Redirects to login if no valid session.
    """
    return WodAppClient.from_session(session, cache=get_api_cache_service())


def get_subscription_service(
    client: Annotated[WodAppClient, Depends(get_client_from_session_for_view)],
) -> SubscriptionService:
    """Create a per-request SubscriptionService."""
    return SubscriptionService(
        client=client,
        google_db=get_google_accounts_service(),
        sync_service=get_calendar_sync_service(),
    )
