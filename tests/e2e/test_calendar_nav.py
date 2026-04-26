"""E2E tests for HTMX calendar navigation and OOB swap sync."""

from datetime import date, datetime, timedelta

import pytest
from playwright.sync_api import expect

from wodplanner.models.calendar import Appointment


def _appt(name: str, d: date, status: str = "open") -> Appointment:
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
        status=status,
    )


@pytest.mark.e2e
def test_calendar_page_loads(page, mock_wodapp_client):
    today = date.today()
    mock_wodapp_client.get_day_schedule.return_value = [_appt("CrossFit", today)]
    page.goto("/calendar")
    expect(page.locator("h1")).to_have_text("Schedule")
    expect(page.locator(".appointment")).to_be_visible()


@pytest.mark.e2e
def test_htmx_prev_day_nav(page, mock_wodapp_client):
    today = date.today()
    yesterday = today - timedelta(days=1)
    mock_wodapp_client.get_day_schedule.side_effect = [
        [_appt("Today CrossFit", today)],
        [_appt("Yesterday CrossFit", yesterday)],
    ]
    page.goto("/calendar")
    expect(page.locator(".current-date")).to_have_text(today.strftime("%B %d, %Y"))

    with page.expect_response(lambda r: f"/calendar/{yesterday.isoformat()}" in r.url):
        page.get_by_title("Previous day").click()

    expect(page.locator(".current-date")).to_have_text(yesterday.strftime("%B %d, %Y"))


@pytest.mark.e2e
def test_htmx_next_day_nav(page, mock_wodapp_client):
    today = date.today()
    tomorrow = today + timedelta(days=1)
    mock_wodapp_client.get_day_schedule.side_effect = [
        [_appt("Today CrossFit", today)],
        [_appt("Tomorrow CrossFit", tomorrow)],
    ]
    page.goto("/calendar")

    with page.expect_response(lambda r: f"/calendar/{tomorrow.isoformat()}" in r.url):
        page.get_by_title("Next day").click()

    expect(page.locator(".current-date")).to_have_text(tomorrow.strftime("%B %d, %Y"))


@pytest.mark.e2e
def test_oob_swap_date_nav_syncs(page, mock_wodapp_client):
    """After HTMX nav, #date-nav OOB swap updates the displayed date."""
    today = date.today()
    yesterday = today - timedelta(days=1)
    mock_wodapp_client.get_day_schedule.side_effect = [
        [_appt("Today", today)],
        [_appt("Yesterday", yesterday)],
    ]
    page.goto("/calendar")

    with page.expect_response(lambda r: f"/calendar/{yesterday.isoformat()}" in r.url):
        page.get_by_title("Previous day").click()

    # #date-nav OOB swap: .current-date text updates
    expect(page.locator("#date-nav .current-date")).to_have_text(
        yesterday.strftime("%B %d, %Y")
    )
    # #filters OOB swap: div still in DOM with correct structure
    expect(page.locator("#filters")).to_be_attached()


@pytest.mark.e2e
def test_calendar_empty_state(page, mock_wodapp_client):
    mock_wodapp_client.get_day_schedule.return_value = []
    page.goto("/calendar")
    expect(page.locator(".empty-state")).to_be_visible()
    expect(page.locator(".empty-state")).to_contain_text("No classes scheduled")
