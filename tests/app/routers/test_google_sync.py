"""Tests for app/routers/google_sync.py — Google Calendar OAuth and sync routes."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from wodplanner.app.config import settings
from wodplanner.app.main import app
from wodplanner.models.auth import AuthSession
from wodplanner.models.google import GoogleAccount
from wodplanner.services import session as cookie_session
from wodplanner.services.login_limiter import limiter


def _make_google_account(
    user_id=42,
    calendar_id="cal123",
    sync_enabled=True,
):
    return GoogleAccount(
        user_id=user_id,
        google_email="user@gmail.com",
        access_token="enc_access",
        refresh_token="enc_refresh",
        token_expiry=None,
        scopes="calendar",
        calendar_id=calendar_id,
        sync_enabled=sync_enabled,
        created_at="2026-01-01T00:00:00",
    )


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
def mock_google_db():
    db = MagicMock()
    db.get_account.return_value = None
    return db


@pytest.fixture
def mock_sync_service():
    svc = MagicMock()
    svc.get_valid_token.return_value = "token"
    svc.sync.return_value = MagicMock(ok=True, inserted=0, updated=0, deleted=0, errors=[])
    return svc


@pytest.fixture
def google_app_client(monkeypatch, db_path, mock_google_db, mock_sync_service):
    from wodplanner.app.dependencies import get_calendar_sync_service, get_google_accounts_service

    monkeypatch.setenv("DB_PATH", str(db_path))
    limiter._state.clear()
    app.dependency_overrides[get_google_accounts_service] = lambda: mock_google_db
    app.dependency_overrides[get_calendar_sync_service] = lambda: mock_sync_service

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    limiter._state.clear()


class TestSettingsPage:
    def test_redirects_when_unauthenticated(self, google_app_client):
        r = google_app_client.get("/settings", follow_redirects=False)
        assert r.status_code in (302, 303)

    def test_renders_when_authenticated(self, google_app_client, session_cookie):
        r = google_app_client.get("/settings", cookies={"session": session_cookie})
        assert r.status_code == 200

    def test_renders_with_connected_account(self, google_app_client, session_cookie, mock_google_db):
        mock_google_db.get_account.return_value = _make_google_account()
        r = google_app_client.get("/settings", cookies={"session": session_cookie})
        assert r.status_code == 200


class TestGoogleConnect:
    def test_returns_503_when_google_not_configured(self, google_app_client, session_cookie, monkeypatch):
        monkeypatch.setattr(settings, "google_client_id", None)
        monkeypatch.setattr(settings, "google_client_secret", None)
        r = google_app_client.get(
            "/google/connect", cookies={"session": session_cookie}, follow_redirects=False
        )
        assert r.status_code == 503

    def test_redirects_to_google_when_configured(self, google_app_client, session_cookie, monkeypatch):
        monkeypatch.setattr(settings, "google_client_id", "test_client_id")
        monkeypatch.setattr(settings, "google_client_secret", "test_client_secret")
        r = google_app_client.get(
            "/google/connect", cookies={"session": session_cookie}, follow_redirects=False
        )
        assert r.status_code == 302
        assert "accounts.google.com" in r.headers["location"]

    def test_sets_g_state_cookie(self, google_app_client, session_cookie, monkeypatch):
        monkeypatch.setattr(settings, "google_client_id", "cid")
        monkeypatch.setattr(settings, "google_client_secret", "csecret")
        r = google_app_client.get(
            "/google/connect", cookies={"session": session_cookie}, follow_redirects=False
        )
        assert "g_state" in r.cookies or "g_state" in r.headers.get("set-cookie", "")


class TestGoogleCallback:
    def test_error_param_redirects_to_settings(self, google_app_client, session_cookie):
        r = google_app_client.get(
            "/google/callback?error=access_denied",
            cookies={"session": session_cookie},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "google_denied" in r.headers["location"]

    def test_missing_code_redirects(self, google_app_client, session_cookie):
        r = google_app_client.get(
            "/google/callback?state=abc",
            cookies={"session": session_cookie},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "google_invalid" in r.headers["location"]

    def test_missing_state_redirects(self, google_app_client, session_cookie):
        r = google_app_client.get(
            "/google/callback?code=abc",
            cookies={"session": session_cookie},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "google_invalid" in r.headers["location"]

    def test_missing_g_state_cookie_redirects(self, google_app_client, session_cookie):
        r = google_app_client.get(
            "/google/callback?code=abc&state=xyz",
            cookies={"session": session_cookie},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "google_state_missing" in r.headers["location"]

    def test_state_mismatch_redirects(self, google_app_client, session_cookie):
        from itsdangerous import URLSafeTimedSerializer

        signed_wrong = URLSafeTimedSerializer(settings.secret_key).dumps("wrong_state")
        r = google_app_client.get(
            "/google/callback?code=abc&state=xyz",
            cookies={"session": session_cookie, "g_state": signed_wrong},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "google_state_mismatch" in r.headers["location"]

    def test_success_stores_account_and_redirects(
        self, google_app_client, session_cookie, mock_google_db, monkeypatch
    ):
        from itsdangerous import URLSafeTimedSerializer

        state = "valid_state_123"
        signed = URLSafeTimedSerializer(settings.secret_key).dumps(state)
        monkeypatch.setattr(settings, "google_client_id", "client_id")
        monkeypatch.setattr(settings, "google_client_secret", "client_secret")
        monkeypatch.setattr(settings, "google_redirect_uri", "https://example.com/cb")

        token_data = {
            "access_token": "raw_access",
            "refresh_token": "raw_refresh",
            "expires_in": 3600,
            "scope": "calendar",
        }
        mock_google_db.upsert_account.return_value = _make_google_account()

        with (
            patch("wodplanner.app.routers.google_sync.exchange_code", return_value=token_data),
            patch("wodplanner.app.routers.google_sync.get_user_email", return_value="user@gmail.com"),
            patch("wodplanner.app.routers.google_sync.crypto.encrypt", return_value="enc"),
        ):
            r = google_app_client.get(
                f"/google/callback?code=authcode&state={state}",
                cookies={"session": session_cookie, "g_state": signed},
                follow_redirects=False,
            )
        assert r.status_code == 303
        assert "google_connected" in r.headers["location"]
        mock_google_db.upsert_account.assert_called_once()

    def test_exchange_failure_redirects_with_error(
        self, google_app_client, session_cookie, monkeypatch
    ):
        from itsdangerous import URLSafeTimedSerializer

        state = "state456"
        signed = URLSafeTimedSerializer(settings.secret_key).dumps(state)
        monkeypatch.setattr(settings, "google_client_id", "client_id")
        monkeypatch.setattr(settings, "google_client_secret", "client_secret")
        monkeypatch.setattr(settings, "google_redirect_uri", "https://example.com/cb")

        with patch("wodplanner.app.routers.google_sync.exchange_code", side_effect=Exception("token exchange failed")):
            r = google_app_client.get(
                f"/google/callback?code=bad_code&state={state}",
                cookies={"session": session_cookie, "g_state": signed},
                follow_redirects=False,
            )
        assert r.status_code == 303
        assert "google_exchange_failed" in r.headers["location"]


class TestGoogleDisconnect:
    def test_redirects_when_no_account(self, google_app_client, session_cookie, mock_google_db):
        mock_google_db.get_account.return_value = None
        r = google_app_client.post(
            "/google/disconnect", cookies={"session": session_cookie}, follow_redirects=False
        )
        assert r.status_code == 303
        assert "google_disconnected" in r.headers["location"]

    def test_revokes_token_and_deletes_account(
        self, google_app_client, session_cookie, mock_google_db
    ):
        mock_google_db.get_account.return_value = _make_google_account()
        with (
            patch("wodplanner.app.routers.google_sync.crypto.decrypt", return_value="raw_token"),
            patch("wodplanner.app.routers.google_sync.revoke_token") as mock_revoke,
        ):
            r = google_app_client.post(
                "/google/disconnect", cookies={"session": session_cookie}, follow_redirects=False
            )
        assert r.status_code == 303
        mock_revoke.assert_called_once_with("raw_token")
        mock_google_db.delete_account.assert_called_once_with(42)

    def test_disconnect_continues_even_if_revoke_raises(
        self, google_app_client, session_cookie, mock_google_db
    ):
        mock_google_db.get_account.return_value = _make_google_account()
        with (
            patch("wodplanner.app.routers.google_sync.crypto.decrypt", return_value="raw_token"),
            patch("wodplanner.app.routers.google_sync.revoke_token", side_effect=Exception("revoke failed")),
        ):
            r = google_app_client.post(
                "/google/disconnect", cookies={"session": session_cookie}, follow_redirects=False
            )
        assert r.status_code == 303
        mock_google_db.delete_account.assert_called_once()


class TestGoogleCalendars:
    def test_returns_400_when_no_account(self, google_app_client, session_cookie, mock_google_db):
        mock_google_db.get_account.return_value = None
        r = google_app_client.get("/google/calendars", cookies={"session": session_cookie})
        assert r.status_code == 400

    def test_returns_calendar_list_html(self, google_app_client, session_cookie, mock_google_db):
        mock_google_db.get_account.return_value = _make_google_account()
        calendars = [{"id": "cal1", "summary": "My Calendar"}]
        with patch("wodplanner.app.routers.google_sync.gcal.list_calendars", return_value=calendars):
            r = google_app_client.get("/google/calendars", cookies={"session": session_cookie})
        assert r.status_code == 200

    def test_returns_empty_calendars_on_error(self, google_app_client, session_cookie, mock_google_db):
        mock_google_db.get_account.return_value = _make_google_account()
        with patch("wodplanner.app.routers.google_sync.gcal.list_calendars", side_effect=Exception("network")):
            r = google_app_client.get("/google/calendars", cookies={"session": session_cookie})
        assert r.status_code == 200


class TestGoogleCalendarSelect:
    def _sync_result(self):
        r = MagicMock()
        r.ok = True
        r.inserted = 1
        r.updated = 0
        r.deleted = 0
        r.errors = []
        return r

    def test_select_existing_calendar(self, google_app_client, session_cookie, mock_google_db, mock_sync_service, monkeypatch):
        account = _make_google_account()
        mock_google_db.get_account.return_value = account
        mock_sync_service.sync.return_value = self._sync_result()
        mock_wodapp_client = MagicMock()
        mock_wodapp_client.get_upcoming_reservations.return_value = ([], {})
        monkeypatch.setattr(
            "wodplanner.app.dependencies.WodAppClient.from_session",
            classmethod(lambda cls, s, cache=None: mock_wodapp_client),
        )

        r = google_app_client.post(
            "/google/calendar/select",
            data={"calendar_choice": "cal_id|My Calendar"},
            cookies={"session": session_cookie},
        )
        assert r.status_code == 200
        mock_google_db.update_calendar.assert_called_once_with(42, "cal_id", "My Calendar")

    def test_select_calendar_without_pipe_uses_id_as_summary(
        self, google_app_client, session_cookie, mock_google_db, mock_sync_service, monkeypatch
    ):
        account = _make_google_account()
        mock_google_db.get_account.return_value = account
        mock_sync_service.sync.return_value = self._sync_result()
        mock_wodapp_client = MagicMock()
        mock_wodapp_client.get_upcoming_reservations.return_value = ([], {})
        monkeypatch.setattr(
            "wodplanner.app.dependencies.WodAppClient.from_session",
            classmethod(lambda cls, s, cache=None: mock_wodapp_client),
        )

        r = google_app_client.post(
            "/google/calendar/select",
            data={"calendar_choice": "only_id"},
            cookies={"session": session_cookie},
        )
        assert r.status_code == 200
        mock_google_db.update_calendar.assert_called_once_with(42, "only_id", "only_id")

    def test_create_new_calendar(
        self, google_app_client, session_cookie, mock_google_db, mock_sync_service, monkeypatch
    ):
        account = _make_google_account()
        mock_google_db.get_account.return_value = account
        mock_sync_service.sync.return_value = self._sync_result()
        mock_wodapp_client = MagicMock()
        mock_wodapp_client.get_upcoming_reservations.return_value = ([], {})
        monkeypatch.setattr(
            "wodplanner.app.dependencies.WodAppClient.from_session",
            classmethod(lambda cls, s, cache=None: mock_wodapp_client),
        )

        new_cal = {"id": "new_cal_id", "summary": "WodPlanner"}
        with patch("wodplanner.app.routers.google_sync.gcal.create_calendar", return_value=new_cal):
            r = google_app_client.post(
                "/google/calendar/select",
                data={"calendar_choice": "__create__"},
                cookies={"session": session_cookie},
            )
        assert r.status_code == 200
        mock_google_db.update_calendar.assert_called_once_with(42, "new_cal_id", "WodPlanner")

    def test_create_calendar_failure_returns_error_partial(
        self, google_app_client, session_cookie, mock_google_db, monkeypatch
    ):
        account = _make_google_account()
        mock_google_db.get_account.return_value = account
        mock_wodapp_client = MagicMock()
        monkeypatch.setattr(
            "wodplanner.app.dependencies.WodAppClient.from_session",
            classmethod(lambda cls, s, cache=None: mock_wodapp_client),
        )

        with patch("wodplanner.app.routers.google_sync.gcal.create_calendar", side_effect=Exception("API error")):
            r = google_app_client.post(
                "/google/calendar/select",
                data={"calendar_choice": "__create__"},
                cookies={"session": session_cookie},
            )
        assert r.status_code == 200

    def test_returns_400_when_no_account(self, google_app_client, session_cookie, mock_google_db, monkeypatch):
        mock_google_db.get_account.return_value = None
        mock_wodapp_client = MagicMock()
        monkeypatch.setattr(
            "wodplanner.app.dependencies.WodAppClient.from_session",
            classmethod(lambda cls, s, cache=None: mock_wodapp_client),
        )
        r = google_app_client.post(
            "/google/calendar/select",
            data={"calendar_choice": "cal_id"},
            cookies={"session": session_cookie},
        )
        assert r.status_code == 400

    def test_token_refresh_failure_returns_error_partial(
        self, google_app_client, session_cookie, mock_google_db, mock_sync_service, monkeypatch
    ):
        account = _make_google_account()
        mock_google_db.get_account.return_value = account
        mock_sync_service.get_valid_token.side_effect = Exception("refresh failed")
        mock_wodapp_client = MagicMock()
        monkeypatch.setattr(
            "wodplanner.app.dependencies.WodAppClient.from_session",
            classmethod(lambda cls, s, cache=None: mock_wodapp_client),
        )

        r = google_app_client.post(
            "/google/calendar/select",
            data={"calendar_choice": "cal_id"},
            cookies={"session": session_cookie},
        )
        assert r.status_code == 200


class TestGoogleSyncNow:
    def test_returns_400_when_no_account(self, google_app_client, session_cookie, mock_google_db, monkeypatch):
        mock_google_db.get_account.return_value = None
        mock_wodapp_client = MagicMock()
        monkeypatch.setattr(
            "wodplanner.app.dependencies.WodAppClient.from_session",
            classmethod(lambda cls, s, cache=None: mock_wodapp_client),
        )
        r = google_app_client.post("/google/sync", cookies={"session": session_cookie})
        assert r.status_code == 400

    def test_returns_400_when_no_calendar_selected(
        self, google_app_client, session_cookie, mock_google_db, monkeypatch
    ):
        mock_google_db.get_account.return_value = _make_google_account(calendar_id=None)
        mock_wodapp_client = MagicMock()
        monkeypatch.setattr(
            "wodplanner.app.dependencies.WodAppClient.from_session",
            classmethod(lambda cls, s, cache=None: mock_wodapp_client),
        )
        r = google_app_client.post("/google/sync", cookies={"session": session_cookie})
        assert r.status_code == 400

    def test_triggers_sync_and_returns_html(
        self, google_app_client, session_cookie, mock_google_db, mock_sync_service, monkeypatch
    ):
        account = _make_google_account()
        mock_google_db.get_account.return_value = account
        sync_result = MagicMock()
        sync_result.ok = True
        sync_result.inserted = 1
        sync_result.updated = 0
        sync_result.deleted = 0
        sync_result.errors = []
        mock_sync_service.sync.return_value = sync_result
        mock_wodapp_client = MagicMock()
        mock_wodapp_client.get_upcoming_reservations.return_value = ([], {})
        monkeypatch.setattr(
            "wodplanner.app.dependencies.WodAppClient.from_session",
            classmethod(lambda cls, s, cache=None: mock_wodapp_client),
        )

        r = google_app_client.post("/google/sync", cookies={"session": session_cookie})
        assert r.status_code == 200


class TestGoogleSyncSection:
    def test_returns_sync_section_html(self, google_app_client, session_cookie, mock_google_db):
        mock_google_db.get_account.return_value = None
        r = google_app_client.get("/google/sync-section", cookies={"session": session_cookie})
        assert r.status_code == 200

    def test_redirects_when_unauthenticated(self, google_app_client):
        r = google_app_client.get("/google/sync-section", follow_redirects=False)
        assert r.status_code in (302, 303)


class TestHelperFunctions:
    def test_token_expiry_iso_with_expires_in(self):
        from wodplanner.app.routers.google_sync import _token_expiry_iso

        result = _token_expiry_iso({"expires_in": 3600})
        assert result is not None
        assert "T" in result  # ISO 8601

    def test_token_expiry_iso_without_expires_in(self):
        from wodplanner.app.routers.google_sync import _token_expiry_iso

        result = _token_expiry_iso({"access_token": "tok"})
        assert result is None

    def test_verify_state_valid(self):
        from itsdangerous import URLSafeTimedSerializer

        from wodplanner.app.routers.google_sync import _verify_state

        signed = URLSafeTimedSerializer(settings.secret_key).dumps("mystate")
        _verify_state(signed, "mystate")  # Must not raise

    def test_verify_state_invalid_signature_raises(self):
        from fastapi import HTTPException

        from wodplanner.app.routers.google_sync import _verify_state

        with pytest.raises(HTTPException) as exc_info:
            _verify_state("not_a_valid_signature", "state")
        assert exc_info.value.status_code == 400

    def test_verify_state_mismatch_raises(self):
        from fastapi import HTTPException
        from itsdangerous import URLSafeTimedSerializer

        from wodplanner.app.routers.google_sync import _verify_state

        signed = URLSafeTimedSerializer(settings.secret_key).dumps("state_A")
        with pytest.raises(HTTPException) as exc_info:
            _verify_state(signed, "state_B")
        assert exc_info.value.status_code == 400
