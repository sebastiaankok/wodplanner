"""Google Calendar OAuth, settings, and sync routes."""

import logging
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeTimedSerializer

from wodplanner.api.client import WodAppClient
from wodplanner.app.config import settings
from wodplanner.app.dependencies import (
    get_client_from_session_for_view,
    get_google_accounts_service,
    get_schedule_service,
    require_session_for_view,
)
from wodplanner.services.schedule import ScheduleService
from wodplanner.models.auth import AuthSession
from wodplanner.services import calendar_sync, crypto
from wodplanner.services import google_calendar as gcal
from wodplanner.services.google_accounts import GoogleAccountsService
from wodplanner.services.google_oauth import (
    build_auth_url,
    exchange_code,
    get_user_email,
    revoke_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["google-calendar"])

_templates_dir = Path(__file__).parent.parent / "templates"
_templates = Jinja2Templates(directory=_templates_dir)


def _render(request: Request, name: str, context: dict):
    return _templates.TemplateResponse(request=request, name=name, context=context)


def _user_context(session: AuthSession) -> dict:
    return {"user": {"firstname": session.firstname, "username": session.username}}


def _google_configured() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


def _enc_key() -> bytes:
    return crypto.get_enc_key(settings.google_token_enc_key, settings.secret_key)


def _sign_state(state: str) -> str:
    return URLSafeTimedSerializer(settings.secret_key).dumps(state)


def _verify_state(signed_cookie: str, state_param: str) -> None:
    try:
        expected = URLSafeTimedSerializer(settings.secret_key).loads(
            signed_cookie, max_age=600
        )
    except BadSignature:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    if expected != state_param:
        raise HTTPException(status_code=400, detail="OAuth state mismatch")


def _token_expiry_iso(token_data: dict) -> str | None:
    if "expires_in" in token_data:
        from datetime import datetime, timedelta
        return (datetime.now() + timedelta(seconds=token_data["expires_in"])).isoformat()
    return None


# ── Routes ───────────────────────────────────────────────────────────────────


@router.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    error: str | None = None,
    success: str | None = None,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    db: GoogleAccountsService = Depends(get_google_accounts_service),
):
    account = db.get_account(session.user_id)
    return _render(
        request,
        "settings.html",
        {
            "active_page": "settings",
            "google_configured": _google_configured(),
            "google_account": account,
            "error": error,
            "success": success,
            **_user_context(session),
        },
    )


@router.get("/google/connect")
def google_connect(
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
):
    if not _google_configured():
        raise HTTPException(status_code=503, detail="Google Calendar not configured")

    state = secrets.token_urlsafe(32)
    auth_url = build_auth_url(
        state=state,
        client_id=settings.google_client_id,  # type: ignore[arg-type]
        redirect_uri=settings.google_redirect_uri,
    )

    response = RedirectResponse(url=auth_url, status_code=302)
    response.set_cookie(
        "g_state",
        _sign_state(state),
        max_age=600,
        httponly=True,
        secure=settings.cookie_secure or False,
        samesite="lax",
    )
    return response


@router.get("/google/callback")
def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    g_state: Annotated[str | None, Cookie()] = None,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    db: GoogleAccountsService = Depends(get_google_accounts_service),
):
    if error:
        logger.warning("Google OAuth error: %s", error)
        return RedirectResponse(url="/settings?error=google_denied", status_code=303)

    if not code or not state:
        return RedirectResponse(url="/settings?error=google_invalid", status_code=303)

    if not g_state:
        return RedirectResponse(url="/settings?error=google_state_missing", status_code=303)

    try:
        _verify_state(g_state, state)
    except HTTPException:
        return RedirectResponse(url="/settings?error=google_state_mismatch", status_code=303)

    try:
        token_data = exchange_code(
            code=code,
            client_id=settings.google_client_id,  # type: ignore[arg-type]
            client_secret=settings.google_client_secret,  # type: ignore[arg-type]
            redirect_uri=settings.google_redirect_uri,
        )
        google_email = get_user_email(token_data["access_token"])
        key = _enc_key()
        db.upsert_account(
            user_id=session.user_id,
            google_email=google_email,
            access_token=crypto.encrypt(token_data["access_token"], key),
            refresh_token=crypto.encrypt(token_data.get("refresh_token", ""), key),
            token_expiry=_token_expiry_iso(token_data),
            scopes=token_data.get("scope", ""),
        )
        # Store WodApp session for periodic background sync.
        db.store_wodapp_session_enc(
            session.user_id,
            crypto.encrypt(session.model_dump_json(), key),
        )
    except Exception:
        logger.exception("Google OAuth callback failed for user %d", session.user_id)
        return RedirectResponse(url="/settings?error=google_exchange_failed", status_code=303)

    response = RedirectResponse(url="/settings?success=google_connected", status_code=303)
    response.delete_cookie("g_state")
    return response


@router.post("/google/disconnect")
def google_disconnect(
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    db: GoogleAccountsService = Depends(get_google_accounts_service),
):
    account = db.get_account(session.user_id)
    if account:
        try:
            raw_token = crypto.decrypt(account.access_token, _enc_key())
            revoke_token(raw_token)
        except Exception:
            pass
        db.delete_account(session.user_id)

    return RedirectResponse(url="/settings?success=google_disconnected", status_code=303)


@router.get("/google/calendars", response_class=HTMLResponse)
def google_calendars(
    request: Request,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    db: GoogleAccountsService = Depends(get_google_accounts_service),
):
    """HTMX partial: list user's Google Calendars for calendar picker."""
    account = db.get_account(session.user_id)
    if not account:
        raise HTTPException(status_code=400, detail="Not connected to Google")

    try:
        access_token = calendar_sync.get_valid_token(account, db, _enc_key())
        calendars = gcal.list_calendars(access_token)
    except Exception:
        logger.exception("Failed to list calendars for user %d", session.user_id)
        calendars = []

    return _render(
        request,
        "partials/google_calendars.html",
        {"google_account": account, "calendars": calendars},
    )


@router.post("/google/calendar/select", response_class=HTMLResponse)
def google_calendar_select(
    request: Request,
    calendar_choice: str = Form(...),
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    client: WodAppClient = Depends(get_client_from_session_for_view),
    db: GoogleAccountsService = Depends(get_google_accounts_service),
    schedule_service: ScheduleService = Depends(get_schedule_service),
):
    """Save the chosen Google Calendar, then run an initial insert-only sync."""
    account = db.get_account(session.user_id)
    if not account:
        raise HTTPException(status_code=400, detail="Not connected to Google")

    key = _enc_key()
    try:
        access_token = calendar_sync.get_valid_token(account, db, key)
    except Exception:
        logger.exception("Token refresh failed for user %d", session.user_id)
        return _render(
            request,
            "partials/google_sync.html",
            {
                "google_configured": _google_configured(),
                "google_account": account,
                "sync_result": None,
                "error": "Token refresh failed. Please reconnect.",
            },
        )

    # Parse compound value: "calendar_id|Calendar Name"
    if "|" in calendar_choice:
        cal_id, cal_summary = calendar_choice.split("|", 1)
    else:
        cal_id = calendar_choice
        cal_summary = calendar_choice

    if cal_id == "__create__":
        try:
            new_cal = gcal.create_calendar(access_token, "WodPlanner")
            cal_id = new_cal["id"]
            cal_summary = new_cal.get("summary", "WodPlanner")
        except Exception:
            logger.exception("Failed to create calendar for user %d", session.user_id)
            return _render(
                request,
                "partials/google_sync.html",
                {
                    "google_configured": _google_configured(),
                    "google_account": account,
                    "sync_result": None,
                    "error": "Failed to create calendar. Please try again.",
                },
            )

    db.update_calendar(session.user_id, cal_id, cal_summary)
    account = db.get_account(session.user_id)

    result = calendar_sync.sync_user(
        account=account,  # type: ignore[arg-type]
        db=db,
        client=client,
        enc_key=key,
        first_name=session.firstname,
        gym_name=session.gym_name,
        schedule_service=schedule_service,
        gym_id=session.gym_id,
    )
    account = db.get_account(session.user_id)

    return _render(
        request,
        "partials/google_sync.html",
        {
            "google_configured": _google_configured(),
            "google_account": account,
            "sync_result": result,
            "error": None,
        },
    )


@router.post("/google/sync", response_class=HTMLResponse)
def google_sync_now(
    request: Request,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    client: WodAppClient = Depends(get_client_from_session_for_view),
    db: GoogleAccountsService = Depends(get_google_accounts_service),
    schedule_service: ScheduleService = Depends(get_schedule_service),
):
    """Trigger a manual sync for the authenticated user."""
    account = db.get_account(session.user_id)
    if not account or not account.calendar_id:
        raise HTTPException(status_code=400, detail="Not connected or no calendar selected")

    result = calendar_sync.sync_user(
        account=account,
        db=db,
        client=client,
        enc_key=_enc_key(),
        first_name=session.firstname,
        gym_name=session.gym_name,
        schedule_service=schedule_service,
        gym_id=session.gym_id,
    )
    account = db.get_account(session.user_id)

    return _render(
        request,
        "partials/google_sync.html",
        {
            "google_configured": _google_configured(),
            "google_account": account,
            "sync_result": result,
            "error": None,
        },
    )


@router.get("/google/sync-section", response_class=HTMLResponse)
def google_sync_section(
    request: Request,
    session: Annotated[AuthSession, Depends(require_session_for_view)] = None,  # type: ignore[assignment]
    db: GoogleAccountsService = Depends(get_google_accounts_service),
):
    """Return the sync section partial (used by HTMX cancel on calendar picker)."""
    account = db.get_account(session.user_id)
    return _render(
        request,
        "partials/google_sync.html",
        {
            "google_configured": _google_configured(),
            "google_account": account,
            "sync_result": None,
            "error": None,
        },
    )
