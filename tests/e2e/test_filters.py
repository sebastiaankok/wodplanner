"""E2E tests for filter toggle JS and filter chip POST persistence."""

import os
from datetime import date, datetime
from pathlib import Path

import pytest
from playwright.sync_api import expect

from wodplanner.models.auth import AuthSession
from wodplanner.models.calendar import Appointment
from wodplanner.services.preferences import PreferencesService


def _appt(name: str, d: date = None) -> Appointment:
    d = d or date.today()
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


# Use a distinct user_id so filter prefs don't bleed into other test files
@pytest.fixture
def auth_session() -> AuthSession:
    return AuthSession(
        token="filter_tok",
        user_id=100,
        appuser_id=1000,
        username="filter@example.com",
        firstname="Filter",
        gym_id=100,
        gym_name="Test Gym",
        agenda_id=5,
    )


@pytest.mark.e2e
def test_filter_panel_hidden_by_default(page, mock_wodapp_client):
    """CSS hides #filters on load; JS controls visibility via toggleFilters()."""
    mock_wodapp_client.get_day_schedule.return_value = []
    page.goto("/calendar")
    expect(page.locator("#filters")).to_have_css("display", "none")


@pytest.mark.e2e
def test_filter_toggle_shows_panel(page, mock_wodapp_client):
    mock_wodapp_client.get_day_schedule.return_value = []
    page.goto("/calendar")
    page.locator("#filters-toggle-btn").click()
    expect(page.locator("#filters")).not_to_have_css("display", "none")


@pytest.mark.e2e
def test_filter_toggle_twice_hides_panel(page, mock_wodapp_client):
    mock_wodapp_client.get_day_schedule.return_value = []
    page.goto("/calendar")
    page.locator("#filters-toggle-btn").click()
    page.locator("#filters-toggle-btn").click()
    expect(page.locator("#filters")).to_have_css("display", "none")


@pytest.mark.e2e
def test_filter_remains_open_after_htmx_nav(page, mock_wodapp_client):
    """filtersOpen state persists: htmx:afterSettle re-applies display:flex."""
    from datetime import timedelta
    today = date.today()
    tomorrow = today + timedelta(days=1)
    mock_wodapp_client.get_day_schedule.side_effect = [
        [_appt("CrossFit", today)],
        [_appt("CrossFit", tomorrow)],
    ]
    page.goto("/calendar")
    page.locator("#filters-toggle-btn").click()
    expect(page.locator("#filters")).not_to_have_css("display", "none")

    with page.expect_response(lambda r: f"/calendar/{tomorrow.isoformat()}" in r.url):
        page.get_by_title("Next day").click()

    # htmx:afterSettle fires and applyFiltersState() keeps panel open
    expect(page.locator("#filters")).not_to_have_css("display", "none")


@pytest.mark.e2e
def test_filter_checkbox_persists_preference(page, mock_wodapp_client, auth_session):
    """Checking 'Open Gym' sends HTMX POST and saves hidden type to DB."""
    today = date.today()
    mock_wodapp_client.get_day_schedule.return_value = [
        _appt("Open Gym", today),
        _appt("CrossFit", today),
    ]

    prefs = PreferencesService(Path(os.environ["DB_PATH"]))
    prefs.toggle_hidden_class_type(auth_session.user_id, "Open Gym")
    prefs.toggle_hidden_class_type(auth_session.user_id, "Open Gym")  # ensure visible on load

    page.goto("/calendar")
    page.locator("#filters-toggle-btn").click()
    expect(page.locator("#filters")).not_to_have_css("display", "none")

    # The filter label wraps the checkbox; filter by label text, then get the input
    open_gym_checkbox = page.locator("label.filter-toggle").filter(
        has_text="Open Gym"
    ).locator("input[type=checkbox]")

    # Tick the checkbox — triggers hx-post="/filters/toggle/Open Gym"
    with page.expect_response(lambda r: "filters/toggle" in r.url):
        open_gym_checkbox.check()

    hidden = prefs.get_hidden_class_types(auth_session.user_id)
    assert "Open Gym" in hidden

    # Clean up
    prefs.toggle_hidden_class_type(auth_session.user_id, "Open Gym")
