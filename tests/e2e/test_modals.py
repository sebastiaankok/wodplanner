"""E2E tests for schedule modal, 1RM modal, and people modal open/close."""

from datetime import date, datetime, timedelta

import pytest
from playwright.sync_api import expect

_TOMORROW = date.today() + timedelta(days=1)
_CALENDAR_URL = f"/calendar?day={_TOMORROW.isoformat()}"

from wodplanner.models.calendar import (
    Appointment,
    AppointmentDetails,
    Member,
    Subscriptions,
    WaitingList,
)


def _appt(name: str = "CrossFit") -> Appointment:
    d = _TOMORROW
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


def _details() -> AppointmentDetails:
    d = _TOMORROW
    start = datetime.combine(d, datetime.strptime("07:00", "%H:%M").time())
    end = datetime.combine(d, datetime.strptime("08:00", "%H:%M").time())
    return AppointmentDetails(
        id_appointment=1,
        id_appointment_type=1,
        name="CrossFit",
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
            subscribed=0, total=1, full=0,
            members=[Member(name="Alice", id_appuser=1001)],
        ),
        waitinglist=WaitingList(total=0, members=[]),
    )


@pytest.mark.e2e
def test_schedule_modal_opens(page, mock_wodapp_client):
    mock_wodapp_client.get_day_schedule.return_value = [_appt()]
    page.goto(_CALENDAR_URL)

    with page.expect_response(lambda r: "/schedule" in r.url):
        page.get_by_title("View workout").first.click()

    expect(page.locator("#schedule-modal")).to_have_class("modal active")
    expect(page.locator("#schedule-modal-content")).to_be_visible()


@pytest.mark.e2e
def test_schedule_modal_closes_on_escape(page, mock_wodapp_client):
    mock_wodapp_client.get_day_schedule.return_value = [_appt()]
    page.goto(_CALENDAR_URL)

    with page.expect_response(lambda r: "/schedule" in r.url):
        page.get_by_title("View workout").first.click()

    page.keyboard.press("Escape")
    expect(page.locator("#schedule-modal")).not_to_have_class("modal active")


@pytest.mark.e2e
def test_schedule_modal_closes_on_close_button(page, mock_wodapp_client):
    mock_wodapp_client.get_day_schedule.return_value = [_appt()]
    page.goto(_CALENDAR_URL)

    with page.expect_response(lambda r: "/schedule" in r.url):
        page.get_by_title("View workout").first.click()

    page.locator(".modal-close").first.click()
    expect(page.locator("#schedule-modal")).not_to_have_class("modal active")


@pytest.mark.e2e
def test_people_modal_close_button(page, mock_wodapp_client):
    mock_wodapp_client.get_day_schedule.return_value = [_appt()]
    mock_wodapp_client.get_appointment_details.return_value = _details()
    page.goto(_CALENDAR_URL)

    with page.expect_response(lambda r: "/people" in r.url):
        page.get_by_title("View participants").first.click()

    expect(page.locator("#people-modal")).to_have_class("modal active")
    page.locator("#people-modal-content .modal-close").click()
    expect(page.locator("#people-modal")).not_to_have_class("modal active")
