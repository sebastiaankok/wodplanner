"""Cookie-based session encoding using signed serialization."""

from itsdangerous import BadSignature, URLSafeTimedSerializer

from wodplanner.models.auth import AuthSession


def encode(auth_session: AuthSession, secret_key: str) -> str:
    """Serialize and sign an AuthSession for storage in a cookie."""
    s = URLSafeTimedSerializer(secret_key)
    return s.dumps(auth_session.model_dump())


def decode(cookie_value: str, secret_key: str, max_age_seconds: int) -> AuthSession | None:
    """Verify and deserialize an AuthSession from a signed cookie value."""
    s = URLSafeTimedSerializer(secret_key)
    try:
        data = s.loads(cookie_value, max_age=max_age_seconds)
        return AuthSession(**data)
    except (BadSignature, Exception):
        return None
