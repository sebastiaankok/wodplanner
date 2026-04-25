"""Tests for app/routers/auth.py."""

from unittest.mock import patch

from wodplanner.api.client import AuthenticationError, WodAppError
from wodplanner.models.auth import AuthSession


class TestGetCurrentUser:
    def test_me_requires_session(self, app_client):
        response = app_client.get("/api/auth/me")
        assert response.status_code == 401

    def test_me_returns_user_info(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/api/auth/me")
        assert response.status_code == 200
        body = response.json()
        assert body["user_id"] == 42
        assert body["username"] == "user@example.com"
        assert body["gym_id"] == 100


class TestLogin:
    def _stub_session(self) -> AuthSession:
        return AuthSession(
            token="newtok",
            user_id=99,
            username="bob@example.com",
            firstname="Bob",
            gym_id=1,
            gym_name="Gym",
        )

    def test_login_success_sets_cookie_and_redirects(self, app_client):
        with patch("wodplanner.app.routers.auth.WodAppClient") as MockClient:
            instance = MockClient.return_value
            instance.login.return_value = self._stub_session()
            response = app_client.post(
                "/api/auth/login",
                data={"username": "bob@example.com", "password": "pw"},
                follow_redirects=False,
            )
        assert response.status_code == 303
        assert response.headers["location"] == "/"
        assert "session=" in response.headers.get("set-cookie", "")

    def test_login_bad_credentials_redirects_with_error(self, app_client):
        with patch("wodplanner.app.routers.auth.WodAppClient") as MockClient:
            MockClient.return_value.login.side_effect = AuthenticationError("bad")
            response = app_client.post(
                "/api/auth/login",
                data={"username": "x", "password": "y"},
                follow_redirects=False,
            )
        assert response.status_code == 303
        assert "Invalid+credentials" in response.headers["location"] or "Invalid%20credentials" in response.headers["location"]

    def test_login_wodapp_error_redirects_with_error(self, app_client):
        with patch("wodplanner.app.routers.auth.WodAppClient") as MockClient:
            MockClient.return_value.login.side_effect = WodAppError("svc down")
            response = app_client.post(
                "/api/auth/login",
                data={"username": "x", "password": "y"},
                follow_redirects=False,
            )
        assert response.status_code == 303
        assert "Login+failed" in response.headers["location"] or "Login%20failed" in response.headers["location"]

    def test_login_rate_limited_after_failures(self, app_client):
        with patch("wodplanner.app.routers.auth.WodAppClient") as MockClient:
            MockClient.return_value.login.side_effect = AuthenticationError("bad")
            # First failed attempt
            app_client.post(
                "/api/auth/login",
                data={"username": "x", "password": "y"},
                follow_redirects=False,
            )
            # Second attempt — should now be blocked
            response = app_client.post(
                "/api/auth/login",
                data={"username": "x", "password": "y"},
                follow_redirects=False,
            )
        assert response.status_code == 303
        assert "Too+many" in response.headers["location"] or "Too%20many" in response.headers["location"]


class TestLogout:
    def test_logout_clears_cookie(self, app_client):
        response = app_client.post("/api/auth/logout", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"
        assert "session=" in response.headers.get("set-cookie", "")
