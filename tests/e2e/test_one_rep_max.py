"""E2E tests for 1RM page: log form toggle, add entry, chart data update."""

import os
from datetime import date
from pathlib import Path

import pytest
from playwright.sync_api import expect

from wodplanner.services.one_rep_max import OneRepMaxService


@pytest.mark.e2e
def test_1rm_page_loads(page):
    page.goto("/1rm")
    expect(page.locator("h1")).to_have_text("1 Rep Max")
    expect(page.get_by_text("+ Log")).to_be_visible()


@pytest.mark.e2e
def test_log_form_hidden_by_default(page):
    page.goto("/1rm")
    expect(page.locator("#log-form-card")).not_to_be_visible()


@pytest.mark.e2e
def test_log_form_toggle_shows_and_hides(page):
    page.goto("/1rm")
    page.get_by_text("+ Log").click()
    expect(page.locator("#log-form-card")).to_be_visible()

    page.get_by_text("+ Log").click()
    expect(page.locator("#log-form-card")).not_to_be_visible()


@pytest.mark.e2e
def test_add_1rm_entry_updates_history(page, auth_session):
    """Submit 1RM form → history partial swaps, entry appears in table."""
    orm_svc = OneRepMaxService(Path(os.environ["DB_PATH"]))

    page.goto("/1rm")
    page.get_by_text("+ Log").click()

    page.locator("select[name=exercise]").select_option("Back Squat")
    page.locator("input[name=weight_kg]").fill("100")
    page.locator("input[name=recorded_at]").fill(date.today().isoformat())

    with page.expect_response(lambda r: "one-rep-maxes/add" in r.url):
        page.get_by_role("button", name="Save").click()

    expect(page.locator("#one-rep-max-history")).to_contain_text("Back Squat")
    expect(page.locator("#one-rep-max-history")).to_contain_text("100.0 kg")
    # Log form closes after successful submit (hx-on::after-request)
    expect(page.locator("#log-form-card")).not_to_be_visible()

    # Clean up: delete the entry we just added
    entries = orm_svc.get_all(auth_session.user_id)
    for e in entries:
        if e.exercise == "Back Squat" and e.weight_kg == 100.0:
            orm_svc.delete(auth_session.user_id, e.id)


@pytest.mark.e2e
def test_delete_1rm_entry_updates_history(page, auth_session):
    """Delete button sends HTMX DELETE → entry removed from history."""
    orm_svc = OneRepMaxService(Path(os.environ["DB_PATH"]))
    orm_svc.add(auth_session.user_id, "Deadlift", 120.0, date.today())

    page.goto("/1rm")
    expect(page.locator("#one-rep-max-history")).to_contain_text("Deadlift")

    page.on("dialog", lambda d: d.accept())

    with page.expect_response(lambda r: "delete" in r.url and r.request.method == "DELETE"):
        page.locator(".btn-delete").first.click()

    expect(page.locator("#one-rep-max-history")).not_to_contain_text("Deadlift")

    # Clean up any remaining entries
    for e in orm_svc.get_all(auth_session.user_id):
        if e.exercise == "Deadlift":
            orm_svc.delete(auth_session.user_id, e.id)
