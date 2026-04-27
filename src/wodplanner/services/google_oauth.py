"""Google OAuth 2.0 helpers for Calendar access."""

from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"
_USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v2/userinfo"


def build_auth_url(state: str, client_id: str, redirect_uri: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "include_granted_scopes": "false",
    }
    return f"{_AUTH_ENDPOINT}?{urlencode(params)}"


def exchange_code(
    code: str, client_id: str, client_secret: str, redirect_uri: str
) -> dict:
    """Exchange authorization code for tokens. Returns raw token response dict."""
    resp = httpx.post(
        _TOKEN_ENDPOINT,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_user_email(access_token: str) -> str:
    """Fetch user email from Google userinfo endpoint."""
    resp = httpx.get(
        _USERINFO_ENDPOINT,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("email", "unknown")


def refresh_access_token(
    refresh_token: str, client_id: str, client_secret: str
) -> tuple[str, str | None]:
    """Refresh access token. Returns (new_access_token, new_expiry_iso)."""
    resp = httpx.post(
        _TOKEN_ENDPOINT,
        data={
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    expiry_iso: str | None = None
    if "expires_in" in data:
        expiry_iso = (datetime.now() + timedelta(seconds=data["expires_in"])).isoformat()

    return data["access_token"], expiry_iso


def revoke_token(token: str) -> None:
    """Revoke token at Google. Best-effort — errors are swallowed."""
    try:
        httpx.post(_REVOKE_ENDPOINT, params={"token": token}, timeout=10)
    except Exception:
        pass
