"""Tests for services/google_oauth.py — Google OAuth2 helpers."""

from unittest.mock import MagicMock, patch

import pytest

from wodplanner.services.google_oauth import (
    build_auth_url,
    exchange_code,
    get_user_email,
    refresh_access_token,
    revoke_token,
)


class TestBuildAuthUrl:
    def test_starts_with_auth_endpoint(self):
        url = build_auth_url("state123", "my-client-id", "https://example.com/cb")
        assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth")

    def test_contains_client_id(self):
        url = build_auth_url("state123", "my-client-id", "https://example.com/cb")
        assert "my-client-id" in url

    def test_contains_redirect_uri(self):
        url = build_auth_url("state123", "client_id", "https://example.com/callback")
        assert "example.com" in url

    def test_contains_state(self):
        url = build_auth_url("mystate", "client_id", "https://example.com/cb")
        assert "mystate" in url

    def test_includes_offline_access(self):
        url = build_auth_url("s", "c", "r")
        assert "offline" in url

    def test_includes_calendar_scope(self):
        url = build_auth_url("s", "c", "r")
        assert "calendar" in url


class TestExchangeCode:
    def test_returns_token_dict(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "tok", "refresh_token": "ref"}
        with patch("httpx.post", return_value=mock_resp):
            result = exchange_code("code", "client_id", "client_secret", "redirect")
        assert result["access_token"] == "tok"
        mock_resp.raise_for_status.assert_called_once()

    def test_raises_on_http_error(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("401 Unauthorized")
        with patch("httpx.post", return_value=mock_resp):
            with pytest.raises(Exception, match="401"):
                exchange_code("bad_code", "c", "s", "r")


class TestGetUserEmail:
    def test_returns_email(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"email": "user@example.com"}
        with patch("httpx.get", return_value=mock_resp):
            result = get_user_email("access_token")
        assert result == "user@example.com"

    def test_returns_unknown_when_email_missing(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        with patch("httpx.get", return_value=mock_resp):
            result = get_user_email("access_token")
        assert result == "unknown"


class TestRefreshAccessToken:
    def test_returns_new_token_and_expiry_iso(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "new_tok", "expires_in": 3600}
        with patch("httpx.post", return_value=mock_resp):
            token, expiry = refresh_access_token("refresh_tok", "client_id", "client_secret")
        assert token == "new_tok"
        assert expiry is not None
        assert "T" in expiry  # ISO 8601 datetime

    def test_expiry_is_none_when_no_expires_in(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "new_tok"}
        with patch("httpx.post", return_value=mock_resp):
            token, expiry = refresh_access_token("refresh_tok", "c", "s")
        assert token == "new_tok"
        assert expiry is None


class TestRevokeToken:
    def test_calls_revoke_endpoint(self):
        with patch("httpx.post") as mock_post:
            revoke_token("some_token")
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "revoke" in str(call_kwargs)

    def test_swallows_network_exceptions(self):
        with patch("httpx.post", side_effect=Exception("network error")):
            revoke_token("token")  # Must not raise
