"""E2E tests for subscribe/unsubscribe and people modal."""

from datetime import date, datetime, timedelta

import pytest
from playwright.sync_api import expect

from wodplanner.models.calendar import (
    Appointment,
    AppointmentDetails,
    Member,
    Subscriptions,
    WaitingList,
)

_TOMORROW = date.today() + timedelta(days=1)
_CALENDAR_URL = f"/calendar?day={_TOMORROW.isoformat()}"


def _appt(
    appt_id: int = 1,
    name: str = "CrossFit",
    status: str = "open",
    d: date = None,
) -> Appointment:
    d = d or _TOMORROW
    start = datetime.combine(d, datetime.strptime("07:00", "%H:%M").time())
    end = datetime.combine(d, datetime.strptime("08:00", "%H:%M").time())
    return Appointment(
        id_appointment=appt_id,
        id_appointment_type=1,
        name=name,
        date_start=start,
        date_end=end,
        max_subscriptions=20,
        total_subscriptions=5,
        status=status,
    )


def _details(name: str = "CrossFit") -> AppointmentDetails:
    d = date.today() + timedelta(days=1)
    start = datetime.combine(d, datetime.strptime("07:00", "%H:%M").time())
    end = datetime.combine(d, datetime.strptime("08:00", "%H:%M").time())
    return AppointmentDetails(
        id_appointment=1,
        id_appointment_type=1,
        name=name,
        date_start=start,
        date_end=end,
        max_subscriptions=20,
        waiting_list=0,
        number_hours_before_subscription_opens=168,
        subscription_open_date="01-01-2026 00:00",
        subscribe_not_opened_yet=0,
        subscribe_closed=0,
        unsubscribe_closed=0,
        subscriptions=Subscriptions(
            subscribed=0,
            total=2,
            full=0,
            members=[
                Member(name="Alice", id_appuser=1001),
                Member(name="Bob", id_appuser=1002),
            ],
        ),
        waitinglist=WaitingList(total=0, members=[]),
    )


@pytest.mark.e2e
def test_subscribe_button_visible_for_open_appointment(page, mock_wodapp_client):
    mock_wodapp_client.get_day_schedule.return_value = [_appt(status="open")]
    page.goto(_CALENDAR_URL)
    expect(page.get_by_text("Sign up")).to_be_visible()


@pytest.mark.e2e
def test_subscribe_refreshes_calendar_content(page, mock_wodapp_client):
    """Click 'Sign up' → HTMX POST → #calendar-content swaps, 'Sign out' appears."""
    open_appt = _appt(status="open")
    subscribed_appt = _appt(status="subscribed")
    mock_wodapp_client.get_day_schedule.side_effect = [
        [open_appt],
        [subscribed_appt],
    ]
    page.goto(_CALENDAR_URL)
    expect(page.get_by_text("Sign up")).to_be_visible()

    with page.expect_response(lambda r: "subscribe" in r.url and r.request.method == "POST"):
        page.get_by_text("Sign up").click()

    expect(page.get_by_text("Sign out")).to_be_visible()


@pytest.mark.e2e
def test_people_modal_opens_with_participants(page, mock_wodapp_client):
    """Click people icon → people modal visible with participant names."""
    mock_wodapp_client.get_day_schedule.return_value = [_appt()]
    mock_wodapp_client.get_appointment_details.return_value = _details()
    page.goto(_CALENDAR_URL)

    with page.expect_response(lambda r: "/people" in r.url):
        page.get_by_title("View participants").first.click()

    expect(page.locator("#people-modal")).to_have_class("modal active")
    expect(page.locator(".person-name").first).to_contain_text("Alice")


@pytest.mark.e2e
def test_people_modal_closes_on_escape(page, mock_wodapp_client):
    mock_wodapp_client.get_day_schedule.return_value = [_appt()]
    mock_wodapp_client.get_appointment_details.return_value = _details()
    page.goto(_CALENDAR_URL)

    with page.expect_response(lambda r: "/people" in r.url):
        page.get_by_title("View participants").first.click()

    expect(page.locator("#people-modal")).to_have_class("modal active")
    page.keyboard.press("Escape")
    expect(page.locator("#people-modal")).not_to_have_class("modal active")
