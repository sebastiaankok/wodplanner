"""E2E tests for mobile/responsive layout (iPhone 13 viewport)."""

from datetime import date, datetime

import pytest
from playwright.sync_api import expect

from wodplanner.app.config import settings
from wodplanner.models.auth import AuthSession
from wodplanner.models.calendar import Appointment
from wodplanner.services import session as cookie_session

_IPHONE_VIEWPORT = {"width": 390, "height": 844}
_IPHONE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)


def _appt(name: str = "CrossFit") -> Appointment:
    d = date.today()
    start = datetime.combine(d, datetime.strptime("07:00", "%H:%M").time())
    end = datetime.combine(d, datetime.strptime("08:00", "%H:%M").time())
    return Appointment(
        id_appointment=1,
        id_appointment_type=1,
        name=name,
        date_start=start,
        date_end=end,
        max_subscriptions=20,
        total_subscriptions=5,
        status="open",
    )


@pytest.fixture
def mobile_context(browser, live_server, mock_wodapp_client):
    auth = AuthSession(
        token="mobile_tok",
        user_id=42,
        appuser_id=4242,
        username="user@example.com",
        firstname="User",
        gym_id=100,
        gym_name="Test Gym",
        agenda_id=5,
    )
    cookie_value = cookie_session.encode(auth, settings.secret_key)
    ctx = browser.new_context(
        base_url=live_server,
        viewport=_IPHONE_VIEWPORT,
        user_agent=_IPHONE_UA,
    )
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
def mobile_page(mobile_context):
    p = mobile_context.new_page()
    yield p
    p.close()


@pytest.mark.e2e
def test_calendar_loads_on_iphone(mobile_page, mock_wodapp_client):
    mock_wodapp_client.get_day_schedule.return_value = [_appt()]
    mobile_page.goto("/calendar")
    expect(mobile_page.locator("h1")).to_have_text("Schedule")
    expect(mobile_page.locator(".navbar")).to_be_visible()
    expect(mobile_page.locator(".appointment")).to_be_visible()


@pytest.mark.e2e
def test_filter_toggle_on_mobile(mobile_page, mock_wodapp_client):
    """Filter toggle button and panel work at iPhone width."""
    mock_wodapp_client.get_day_schedule.return_value = []
    mobile_page.goto("/calendar")
    expect(mobile_page.locator("#filters")).to_have_css("display", "none")

    mobile_page.locator("#filters-toggle-btn").click()
    expect(mobile_page.locator("#filters")).not_to_have_css("display", "none")


@pytest.mark.e2e
def test_nav_links_visible_on_mobile(mobile_page, mock_wodapp_client):
    mock_wodapp_client.get_day_schedule.return_value = []
    mobile_page.goto("/calendar")
    # Nav links should be in the DOM (CSS may stack them but they exist)
    expect(mobile_page.locator(".nav-links a[href='/calendar']")).to_be_attached()
    expect(mobile_page.locator(".nav-links a[href='/friends']")).to_be_attached()
