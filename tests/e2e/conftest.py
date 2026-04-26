"""E2E fixtures: live FastAPI server + authenticated Playwright context."""

import os
import socket
import threading
import time
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from wodplanner.api.client import WodAppClient
from wodplanner.app.config import settings
from wodplanner.models.auth import AuthSession
from wodplanner.services import migrations
from wodplanner.services import session as cookie_session
from wodplanner.services.preferences import PreferencesService

_ALL_TOOLTIPS = ["filter", "today", "date_picker", "friends", "schedule", "1rm"]

# Per-test WodAppClient mock — server thread reads _mock_holder[0] on every request
_mock_holder: list = [None]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_server(tmp_path_factory):
    """Start the FastAPI app on a background thread; yield its base URL."""
    import uvicorn

    from wodplanner.app.dependencies import (
        get_api_cache_service,
        get_friends_service,
        get_one_rep_max_service,
        get_preferences_service,
        get_schedule_service,
    )
    from wodplanner.app.main import app

    db_path = tmp_path_factory.mktemp("e2e") / "test.db"
    os.environ["DB_PATH"] = str(db_path)

    for fn in (
        get_friends_service,
        get_preferences_service,
        get_schedule_service,
        get_one_rep_max_service,
        get_api_cache_service,
    ):
        fn.cache_clear()

    migrations.ensure_migrations(db_path)

    original_from_session = WodAppClient.__dict__["from_session"]
    WodAppClient.from_session = classmethod(  # type: ignore[assignment]
        lambda cls, s, cache=None: _mock_holder[0]
    )

    port = _free_port()
    config = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="error", ws="wsproto"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 10.0
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5)
            break
        except Exception:
            time.sleep(0.05)
    else:
        raise RuntimeError("Live server did not start within 10 seconds")

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=5)
    WodAppClient.from_session = original_from_session  # type: ignore[assignment]


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
def mock_wodapp_client() -> MagicMock:
    mock = MagicMock(spec=WodAppClient)
    mock.get_upcoming_reservations.return_value = ([], {})
    mock.get_day_schedule.return_value = []
    _mock_holder[0] = mock
    yield mock
    _mock_holder[0] = None


@pytest.fixture
def authed_context(browser, live_server, auth_session):
    cookie_value = cookie_session.encode(auth_session, settings.secret_key)
    ctx = browser.new_context(base_url=live_server)
    ctx.add_cookies([{
        "name": "session",
        "value": cookie_value,
        "domain": "127.0.0.1",
        "path": "/",
        "httpOnly": True,
        "sameSite": "Lax",
    }])
    yield ctx
    ctx.close()


@pytest.fixture
def page(authed_context, mock_wodapp_client, auth_session):
    prefs = PreferencesService(Path(os.environ["DB_PATH"]))
    for t in _ALL_TOOLTIPS:
        prefs.dismiss_tooltip(auth_session.user_id, t)
    p = authed_context.new_page()
    yield p
    p.close()


@pytest.fixture
def unauthed_page(browser, live_server):
    ctx = browser.new_context(base_url=live_server)
    p = ctx.new_page()
    yield p
    p.close()
    ctx.close()
