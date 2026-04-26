"""E2E tests for friends management and per-user scoping."""

import os
from pathlib import Path

import pytest
from playwright.sync_api import expect

from wodplanner.models.auth import AuthSession
from wodplanner.services.friends import FriendsService


def _friends_svc() -> FriendsService:
    return FriendsService(Path(os.environ["DB_PATH"]))


# Distinct user_ids to avoid state leaking between test files
@pytest.fixture
def auth_session() -> AuthSession:
    return AuthSession(
        token="friends_tok",
        user_id=200,
        appuser_id=2000,
        username="friends@example.com",
        firstname="Friends",
        gym_id=100,
        gym_name="Test Gym",
        agenda_id=5,
    )


@pytest.fixture
def auth_session_b() -> AuthSession:
    return AuthSession(
        token="friends_tok_b",
        user_id=201,
        appuser_id=2001,
        username="friendsb@example.com",
        firstname="FriendsB",
        gym_id=100,
        gym_name="Test Gym",
        agenda_id=5,
    )


@pytest.mark.e2e
def test_friends_page_empty_state(page):
    page.goto("/friends")
    expect(page.locator("h1")).to_have_text("Friends")
    expect(page.locator(".empty-state")).to_be_visible()
    expect(page.locator(".empty-state")).to_contain_text("No friends yet")


@pytest.mark.e2e
def test_delete_friend_via_htmx(page, auth_session):
    """Seed a friend, load page, click Remove → HTMX DELETE → friend gone."""
    svc = _friends_svc()
    svc.add(auth_session.user_id, 9001, "Alice")

    page.goto("/friends")
    expect(page.locator("td strong")).to_contain_text("Alice")

    page.on("dialog", lambda d: d.accept())

    with page.expect_response(lambda r: "delete" in r.url and r.request.method == "DELETE"):
        page.get_by_text("Remove").first.click()

    expect(page.locator(".empty-state")).to_be_visible()

    # Ensure clean state
    for f in svc.get_all(auth_session.user_id):
        svc.delete(auth_session.user_id, f.id)


@pytest.mark.e2e
def test_per_user_friend_scoping(
    browser, live_server, auth_session, auth_session_b, mock_wodapp_client
):
    """Friends added for user A are invisible to user B."""
    from wodplanner.app.config import settings
    from wodplanner.services import session as cookie_session

    svc = _friends_svc()
    svc.add(auth_session.user_id, 9002, "Bob")

    def _make_page(session: AuthSession):
        cookie_value = cookie_session.encode(session, settings.secret_key)
        ctx = browser.new_context(base_url=live_server)
        ctx.add_cookies([{
            "name": "session",
            "value": cookie_value,
            "domain": "127.0.0.1",
            "path": "/",
            "httpOnly": True,
            "sameSite": "Lax",
        }])
        return ctx.new_page(), ctx

    page_a, ctx_a = _make_page(auth_session)
    page_b, ctx_b = _make_page(auth_session_b)

    page_a.goto("/friends")
    expect(page_a.locator("td strong")).to_contain_text("Bob")

    page_b.goto("/friends")
    expect(page_b.locator(".empty-state")).to_be_visible()

    page_a.close(); ctx_a.close()
    page_b.close(); ctx_b.close()

    # Clean up
    for f in svc.get_all(auth_session.user_id):
        svc.delete(auth_session.user_id, f.id)
