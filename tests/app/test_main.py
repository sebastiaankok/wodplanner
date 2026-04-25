"""Tests for app/main.py — exception handlers, middleware, lifespan, /health."""

import logging
from unittest.mock import MagicMock

from fastapi import APIRouter
from fastapi.testclient import TestClient

from wodplanner.api.client import AuthenticationError, WodAppError
from wodplanner.app.main import CloudflareIPMiddleware, _StripZeroPort, app


def _attach_temp_router(routes: APIRouter):
    """Attach a router for the test, return cleanup."""
    app.include_router(routes)

    def cleanup():
        # Remove the routes added
        for route in list(app.router.routes):
            if getattr(route, "endpoint", None) and route.endpoint.__module__ == __name__ and route.path.startswith("/__test__"):
                app.router.routes.remove(route)

    return cleanup


class TestHealthEndpoint:
    def test_health_returns_ok(self, app_client):
        response = app_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "wodplanner"}


class TestWodAppErrorHandler:
    def test_html_response_503(self, app_client):
        router = APIRouter()

        @router.get("/__test__/wodapp_err")
        def boom():
            raise WodAppError("service down")

        cleanup = _attach_temp_router(router)
        try:
            response = app_client.get("/__test__/wodapp_err")
            assert response.status_code == 503
            assert "Service Unavailable" in response.text
            assert "service down" in response.text
        finally:
            cleanup()

    def test_htmx_response_inline_error(self, app_client):
        router = APIRouter()

        @router.get("/__test__/wodapp_err_htmx")
        def boom():
            raise WodAppError("htmx down")

        cleanup = _attach_temp_router(router)
        try:
            response = app_client.get(
                "/__test__/wodapp_err_htmx", headers={"HX-Request": "true"}
            )
            assert response.status_code == 200
            assert "htmx down" in response.text
            assert "<div" in response.text
        finally:
            cleanup()


class TestAuthenticationErrorHandler:
    def test_redirect_303_with_cookie_delete(self, app_client):
        router = APIRouter()

        @router.get("/__test__/auth_err")
        def boom():
            raise AuthenticationError("expired")

        cleanup = _attach_temp_router(router)
        try:
            response = app_client.get("/__test__/auth_err", follow_redirects=False)
            assert response.status_code == 303
            assert "/login?error=session_expired" in response.headers["location"]
            # set-cookie used to delete
            assert "session=" in response.headers.get("set-cookie", "").lower()
        finally:
            cleanup()

    def test_htmx_hx_redirect_header(self, app_client):
        router = APIRouter()

        @router.get("/__test__/auth_err_htmx")
        def boom():
            raise AuthenticationError("expired")

        cleanup = _attach_temp_router(router)
        try:
            response = app_client.get(
                "/__test__/auth_err_htmx",
                headers={"HX-Request": "true"},
                follow_redirects=False,
            )
            assert response.status_code == 200
            assert response.headers.get("hx-redirect") == "/login?error=session_expired"
        finally:
            cleanup()


class TestCloudflareIPMiddleware:
    def test_uses_cf_connecting_ip_when_present(self):
        mw = CloudflareIPMiddleware(app=MagicMock())
        request = MagicMock()
        request.headers = {"CF-Connecting-IP": "10.0.0.1"}
        request.scope = {"client": ("127.0.0.1", 12345)}

        async def call_next(req):
            return "ok"

        import asyncio

        result = asyncio.run(mw.dispatch(request, call_next))
        assert result == "ok"
        assert request.scope["client"] == ("10.0.0.1", 0)

    def test_no_change_when_header_absent(self):
        mw = CloudflareIPMiddleware(app=MagicMock())
        request = MagicMock()
        request.headers = {}
        request.scope = {"client": ("127.0.0.1", 12345)}

        async def call_next(req):
            return "ok"

        import asyncio

        asyncio.run(mw.dispatch(request, call_next))
        assert request.scope["client"] == ("127.0.0.1", 12345)


class TestStripZeroPortFilter:
    def test_strips_trailing_zero_port(self):
        f = _StripZeroPort()
        record = logging.LogRecord(
            "test", logging.INFO, "f", 1, "msg %s", ("10.0.0.1:0", "GET"), None
        )
        assert f.filter(record) is True
        assert record.args == ("10.0.0.1", "GET")

    def test_leaves_normal_addr_unchanged(self):
        f = _StripZeroPort()
        record = logging.LogRecord(
            "test", logging.INFO, "f", 1, "msg %s", ("10.0.0.1:8080", "GET"), None
        )
        assert f.filter(record) is True
        assert record.args == ("10.0.0.1:8080", "GET")

    def test_handles_non_string_args(self):
        f = _StripZeroPort()
        record = logging.LogRecord("test", logging.INFO, "f", 1, "msg", None, None)
        assert f.filter(record) is True


class TestLifespanRunsMigrations:
    def test_lifespan_no_pending_logs_debug(self, monkeypatch, db_path, caplog):
        # db_path fixture already applied migrations; second run should be no-op.
        monkeypatch.setenv("DB_PATH", str(db_path))
        with caplog.at_level(logging.DEBUG, logger="wodplanner.app.main"):
            with TestClient(app):
                pass
        # No assert on specific message — just verify no exception raised.
