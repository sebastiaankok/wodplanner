"""E2E tests for login and authentication flows."""

import re
import pytest
from playwright.sync_api import expect
from unittest.mock import patch

from wodplanner.api.client import AuthenticationError
from wodplanner.services.login_limiter import limiter


@pytest.mark.e2e
def test_unauthenticated_root_redirects_to_login(unauthed_page):
    unauthed_page.goto("/")
    expect(unauthed_page).to_have_url(re.compile(r"/login"))


@pytest.mark.e2e
def test_login_page_renders_form(unauthed_page):
    unauthed_page.goto("/login")
    expect(unauthed_page.locator("input[name=username]")).to_be_visible()
    expect(unauthed_page.locator("input[name=password]")).to_be_visible()
    expect(unauthed_page.locator("button[type=submit]")).to_be_visible()


@pytest.mark.e2e
def test_login_bad_credentials_shows_error(unauthed_page):
    limiter._state.clear()
    unauthed_page.goto("/login")
    with patch("wodplanner.app.routers.auth.WodAppClient") as MockClient:
        MockClient.return_value.login.side_effect = AuthenticationError("bad creds")
        unauthed_page.fill("input[name=username]", "bad@example.com")
        unauthed_page.fill("input[name=password]", "wrong")
        unauthed_page.click("button[type=submit]")
    expect(unauthed_page.locator(".login-error")).to_be_visible()
    expect(unauthed_page.locator(".login-error")).to_contain_text("Invalid")
    limiter._state.clear()


@pytest.mark.e2e
def test_login_rate_limited_after_failures(unauthed_page):
    limiter._state.clear()
    unauthed_page.goto("/login")
    with patch("wodplanner.app.routers.auth.WodAppClient") as MockClient:
        MockClient.return_value.login.side_effect = AuthenticationError("bad")
        # First failure — blocks the IP for 5 s
        unauthed_page.fill("input[name=username]", "x@x.com")
        unauthed_page.fill("input[name=password]", "bad")
        unauthed_page.click("button[type=submit]")
        # Second attempt — should be rate-limited immediately
        unauthed_page.fill("input[name=username]", "x@x.com")
        unauthed_page.fill("input[name=password]", "bad")
        unauthed_page.click("button[type=submit]")
    expect(unauthed_page.locator(".login-error")).to_contain_text("Too many")
    limiter._state.clear()
