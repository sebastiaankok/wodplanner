"""Google Calendar OAuth and settings routes."""

import logging
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeTimedSerializer

from wodplanner.app.config import settings
from wodplanner.app.dependencies import get_google_accounts_service, require_session_for_view
from wodplanner.models.auth import AuthSession
from wodplanner.services import crypto
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
