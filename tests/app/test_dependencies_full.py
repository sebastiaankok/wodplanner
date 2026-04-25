"""Full coverage of app/dependencies.py auth helpers."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from wodplanner.app.config import settings
from wodplanner.app.dependencies import (
    get_client_from_session,
    get_client_from_session_for_view,
    get_friends_service,
    get_one_rep_max_service,
    get_preferences_service,
    get_schedule_service,
    get_session_from_cookie,
    require_session,
    require_session_for_view,
)
from wodplanner.models.auth import AuthSession
from wodplanner.services import session as cookie_session


@pytest.fixture
def auth_session() -> AuthSession:
    return AuthSession(
        token="t",
        user_id=1,
        username="u",
        firstname="F",
        gym_id=10,
        gym_name="G",
    )


class TestGetSessionFromCookie:
    def test_none_cookie_returns_none(self):
        assert get_session_from_cookie(session=None) is None

    def test_empty_cookie_returns_none(self):
        assert get_session_from_cookie(session="") is None

    def test_invalid_cookie_returns_none(self):
        assert get_session_from_cookie(session="garbage") is None

    def test_valid_cookie_returns_session(self, auth_session):
        encoded = cookie_session.encode(auth_session, settings.secret_key)
        result = get_session_from_cookie(session=encoded)
        assert result is not None
        assert result.user_id == 1

    def test_max_age_passed_when_expire_set(self, monkeypatch, auth_session):
        monkeypatch.setattr(settings, "session_expire_days", 7)
        encoded = cookie_session.encode(auth_session, settings.secret_key)
        result = get_session_from_cookie(session=encoded)
        assert result is not None


class TestRequireSession:
    def test_raises_401_when_none(self):
        with pytest.raises(HTTPException) as exc:
            require_session(session=None)
        assert exc.value.status_code == 401

    def test_returns_session_when_present(self, auth_session):
        assert require_session(session=auth_session) is auth_session


class TestRequireSessionForView:
    def test_redirect_303_when_no_session(self):
        request = MagicMock()
        request.headers = {}
        with pytest.raises(HTTPException) as exc:
            require_session_for_view(request=request, session=None)
        assert exc.value.status_code == 303
        assert exc.value.headers["Location"] == "/login"

    def test_htmx_redirect_when_no_session(self):
        request = MagicMock()
        request.headers = {"HX-Request": "true"}
        with pytest.raises(HTTPException) as exc:
            require_session_for_view(request=request, session=None)
        assert exc.value.headers["HX-Redirect"] == "/login"

    def test_returns_session_when_present(self, auth_session):
        request = MagicMock()
        request.headers = {}
        assert require_session_for_view(request=request, session=auth_session) is auth_session


class TestGetClientFromSession:
    def test_creates_client_with_session(self, auth_session):
        client = get_client_from_session(session=auth_session)
        assert client.is_authenticated is True
        assert client.session.token == "t"

    def test_view_variant_creates_client(self, auth_session):
        client = get_client_from_session_for_view(session=auth_session)
        assert client.is_authenticated is True


class TestServiceFactories:
    def test_friends_service_singleton(self, monkeypatch, db_path):
        monkeypatch.setenv("DB_PATH", str(db_path))
        get_friends_service.cache_clear()
        a = get_friends_service()
        b = get_friends_service()
        assert a is b

    def test_preferences_service_singleton(self, monkeypatch, db_path):
        monkeypatch.setenv("DB_PATH", str(db_path))
        get_preferences_service.cache_clear()
        assert get_preferences_service() is get_preferences_service()

    def test_schedule_service_singleton(self, monkeypatch, db_path):
        monkeypatch.setenv("DB_PATH", str(db_path))
        get_schedule_service.cache_clear()
        assert get_schedule_service() is get_schedule_service()

    def test_one_rep_max_service_singleton(self, monkeypatch, db_path):
        monkeypatch.setenv("DB_PATH", str(db_path))
        get_one_rep_max_service.cache_clear()
        assert get_one_rep_max_service() is get_one_rep_max_service()
