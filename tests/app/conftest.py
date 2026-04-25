"""Shared fixtures for FastAPI route tests."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from wodplanner.api.client import WodAppClient
from wodplanner.app.config import settings
from wodplanner.app.dependencies import (
    get_api_cache_service,
    get_friends_service,
    get_one_rep_max_service,
    get_preferences_service,
    get_schedule_service,
)
from wodplanner.models.auth import AuthSession
from wodplanner.services import session as cookie_session
from wodplanner.services.friends import FriendsService
from wodplanner.services.login_limiter import limiter
from wodplanner.services.one_rep_max import OneRepMaxService
from wodplanner.services.preferences import PreferencesService
from wodplanner.services.schedule import ScheduleService


def _clear_dep_caches() -> None:
    for fn in (
        get_friends_service,
        get_preferences_service,
        get_schedule_service,
        get_one_rep_max_service,
        get_api_cache_service,
    ):
        fn.cache_clear()


@pytest.fixture(autouse=True)
def _isolate_dependency_caches(monkeypatch, db_path):
    """Point every per-test FastAPI dep at a fresh tmp DB; reset rate limiter."""
    monkeypatch.setenv("DB_PATH", str(db_path))
    _clear_dep_caches()
    limiter._state.clear()
    yield
    _clear_dep_caches()
    limiter._state.clear()


@pytest.fixture
def auth_session() -> AuthSession:
    return AuthSession(
        token="test_token",
        user_id=42,
        appuser_id=4242,
        username="user@example.com",
        firstname="User",
        gym_id=100,
        gym_name="Test Gym",
        agenda_id=5,
    )


@pytest.fixture
def session_cookie(auth_session: AuthSession) -> str:
    return cookie_session.encode(auth_session, settings.secret_key)


@pytest.fixture
def mock_wodapp_client() -> MagicMock:
    return MagicMock(spec=WodAppClient)


@pytest.fixture
def app_client(monkeypatch, mock_wodapp_client):
    """TestClient with WodAppClient.from_session patched to return a MagicMock.

    Patching at from_session preserves the require_session auth chain so 401
    behavior remains testable, while still letting tests stub API calls.
    """
    from wodplanner.app import dependencies as deps_mod
    from wodplanner.app.main import app
    from wodplanner.app.routers import appointments as appt_mod
    from wodplanner.app.routers import calendar as cal_mod
    from wodplanner.app.routers import views as views_mod

    def _from_session(session, cache=None):
        return mock_wodapp_client

    for mod in (deps_mod, appt_mod, cal_mod, views_mod):
        if hasattr(mod, "WodAppClient"):
            monkeypatch.setattr(mod.WodAppClient, "from_session", classmethod(lambda cls, s, cache=None: mock_wodapp_client))

    monkeypatch.setattr(WodAppClient, "from_session", classmethod(lambda cls, s, cache=None: mock_wodapp_client))

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def friends_service(db_path) -> FriendsService:
    return FriendsService(db_path)


@pytest.fixture
def schedule_service(db_path) -> ScheduleService:
    return ScheduleService(db_path)


@pytest.fixture
def preferences_service(db_path) -> PreferencesService:
    return PreferencesService(db_path)


@pytest.fixture
def one_rep_max_service(db_path) -> OneRepMaxService:
    return OneRepMaxService(db_path)
