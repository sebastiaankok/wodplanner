"""Cookie-based session encoding with encrypted payload and signed serialization."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, URLSafeTimedSerializer

from wodplanner.models.auth import AuthSession


def _derive_fernet_key(secret_key: str) -> bytes:
    """Derive a 32-byte URL-safe Fernet key from the application secret key."""
    digest = hashlib.sha256(secret_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encode(auth_session: AuthSession, secret_key: str) -> str:
    """Serialize, encrypt, and sign an AuthSession for storage in a cookie."""
    f = Fernet(_derive_fernet_key(secret_key))
    data = auth_session.model_dump_json().encode()
    return f.encrypt(data).decode()


def decode(cookie_value: str, secret_key: str, max_age_seconds: int | None) -> AuthSession | None:
    """Verify and deserialize an AuthSession from a cookie value.

    Tries the new encrypted (Fernet) format first, then falls back to the
    old signed-only (URLSafeTimedSerializer) format for backward compatibility.
    """
    session, _ = _decode_with_upgrade(cookie_value, secret_key, max_age_seconds)
    return session


def decode_and_upgrade(
    cookie_value: str, secret_key: str, max_age_seconds: int | None
) -> tuple[AuthSession | None, str | None]:
    """Decode a cookie and return (session, upgraded_cookie_value or None).

    If the cookie was in old signed-only format, upgraded_cookie_value is the
    re-encrypted (Fernet) version so callers can transparently upgrade the cookie.
    If already in new format, invalid, or expired, upgraded_cookie_value is None.
    """
    return _decode_with_upgrade(cookie_value, secret_key, max_age_seconds)


def _decode_with_upgrade(
    cookie_value: str, secret_key: str, max_age_seconds: int | None
) -> tuple[AuthSession | None, str | None]:
    """Shared implementation for decode and decode_and_upgrade."""
    if max_age_seconds is None or max_age_seconds > 0:
        try:
            f = Fernet(_derive_fernet_key(secret_key))
            data = f.decrypt(cookie_value.encode(), ttl=max_age_seconds)
            return AuthSession.model_validate_json(data), None
        except InvalidToken:
            pass

    s = URLSafeTimedSerializer(secret_key)
    try:
        data = s.loads(cookie_value, max_age=max_age_seconds)
        session = AuthSession(**data)
        upgraded = encode(session, secret_key)
        return session, upgraded
    except (BadSignature, Exception):
        return None, None
