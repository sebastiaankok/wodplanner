"""Tests for services/calendar_sync.py — full-diff sync engine."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from wodplanner.models.google import GoogleAccount, SyncedEvent
from wodplanner.services import calendar_sync
from wodplanner.services.calendar_sync import SyncResult


def _make_account(
    user_id=1,
    calendar_id="cal_id",
    token_expiry=None,
    access_token="enc_access",
    refresh_token="enc_refresh",
):
    return GoogleAccount(
        user_id=user_id,
        google_email="user@gmail.com",
        access_token=access_token,
        refresh_token=refresh_token,
        token_expiry=token_expiry,
        scopes="calendar",
        calendar_id=calendar_id,
        sync_enabled=True,
        created_at=datetime.now().isoformat(),
    )


def _make_db(synced_events=None):
    db = MagicMock()
    db.get_synced_events.return_value = synced_events or []
    return db


def _make_client(reservations=None):
    client = MagicMock()
    client.get_upcoming_reservations.return_value = (reservations or [], {})
    return client


def _make_reservation(appt_id=1, name="CrossFit", date_start=None, date_end=None):
    return {
        "id_appointment": appt_id,
        "name": name,
        "date_start": date_start or datetime(2026, 5, 1, 10, 0),
        "date_end": date_end,
    }


def _make_synced_event(appt_id=1, google_event_id="gev1", date_start=None, name="CrossFit"):
    return SyncedEvent(
        user_id=1,
        id_appointment=appt_id,
        google_event_id=google_event_id,
        calendar_id="cal_id",
        date_start=(date_start or datetime(2026, 5, 1, 10, 0)).isoformat(),
        date_end=(date_start or datetime(2026, 5, 1, 11, 0)).isoformat(),
        name=name,
        etag=None,
        synced_at=datetime.now().isoformat(),
    )


ENC_KEY = b"A" * 44  # Placeholder — crypto is mocked


class TestSyncResult:
    def test_ok_true_when_no_errors(self):
        assert SyncResult().ok is True

    def test_ok_false_when_errors_present(self):
        assert SyncResult(errors=["something failed"]).ok is False

    def test_default_counts_are_zero(self):
        r = SyncResult()
        assert r.inserted == 0
        assert r.updated == 0
        assert r.deleted == 0


class TestGetValidToken:
    def test_returns_decrypted_token_when_no_expiry(self):
        account = _make_account(token_expiry=None)
        with patch("wodplanner.services.calendar_sync.crypto.decrypt", return_value="raw_token"):
            token = calendar_sync.get_valid_token(account, _make_db(), ENC_KEY)
        assert token == "raw_token"

    def test_returns_decrypted_token_when_expiry_is_far_future(self):
        far_future = (datetime.now() + timedelta(hours=2)).isoformat()
        account = _make_account(token_expiry=far_future)
        with patch("wodplanner.services.calendar_sync.crypto.decrypt", return_value="raw_token"):
            token = calendar_sync.get_valid_token(account, _make_db(), ENC_KEY)
        assert token == "raw_token"

    def test_refreshes_when_token_near_expiry(self):
        near_expiry = (datetime.now() + timedelta(minutes=2)).isoformat()
        account = _make_account(token_expiry=near_expiry)
        db = _make_db()
        with (
            patch("wodplanner.services.calendar_sync.crypto.decrypt", side_effect=["enc_access", "enc_refresh"]),
            patch("wodplanner.services.calendar_sync.refresh_access_token", return_value=("new_tok", "new_expiry")),
            patch("wodplanner.services.calendar_sync.crypto.encrypt", return_value="enc_new_tok"),
        ):
            token = calendar_sync.get_valid_token(account, db, ENC_KEY)
        assert token == "new_tok"
        db.update_tokens.assert_called_once()

    def test_no_refresh_when_not_near_expiry(self):
        far_future = (datetime.now() + timedelta(hours=2)).isoformat()
        account = _make_account(token_expiry=far_future)
        db = _make_db()
        with patch("wodplanner.services.calendar_sync.crypto.decrypt", return_value="raw_token"):
            calendar_sync.get_valid_token(account, db, ENC_KEY)
        db.update_tokens.assert_not_called()


class TestBuildEvent:
    def test_builds_event_with_explicit_date_end(self):
        start = datetime(2026, 5, 1, 10, 0)
        end = datetime(2026, 5, 1, 11, 0)
        reservation = _make_reservation(appt_id=42, name="Gymnastics", date_start=start, date_end=end)
        event = calendar_sync._build_event(reservation, "Box Gym", "Alice")
        assert event["summary"] == "Alice - Gymnastics"
        assert event["location"] == "Box Gym"
        assert event["end"]["dateTime"] == end.isoformat()
        assert event["extendedProperties"]["private"]["wodplanner_appointment_id"] == "42"

    def test_uses_default_1h_duration_when_no_date_end(self):
        start = datetime(2026, 5, 1, 10, 0)
        reservation = _make_reservation(appt_id=1, date_start=start, date_end=None)
        event = calendar_sync._build_event(reservation, "Gym", "Bob")
        expected_end = start + timedelta(hours=1)
        assert event["end"]["dateTime"] == expected_end.isoformat()

    def test_timezone_is_amsterdam(self):
        reservation = _make_reservation()
        event = calendar_sync._build_event(reservation, "Gym", "Alice")
        assert event["start"]["timeZone"] == "Europe/Amsterdam"
        assert event["end"]["timeZone"] == "Europe/Amsterdam"


class TestRebuildFromGoogle:
    def test_returns_empty_when_no_calendar_id(self):
        account = _make_account(calendar_id=None)
        result = calendar_sync._rebuild_from_google("token", account, _make_db())
        assert result == {}

    def test_rebuilds_synced_events_from_google(self):
        account = _make_account()
        db = _make_db()
        events = [
            {
                "id": "gev1",
                "start": {"dateTime": "2026-05-01T10:00:00"},
                "end": {"dateTime": "2026-05-01T11:00:00"},
                "summary": "Alice - CrossFit",
                "etag": "etag1",
                "extendedProperties": {"private": {"wodplanner_appointment_id": "42"}},
            }
        ]
        with patch("wodplanner.services.calendar_sync.gcal.list_events_in_range", return_value=events):
            result = calendar_sync._rebuild_from_google("token", account, db)
        assert 42 in result
        assert result[42].google_event_id == "gev1"
        db.upsert_synced_event.assert_called_once()

    def test_skips_events_without_appointment_property(self):
        account = _make_account()
        events = [{"id": "ev1", "start": {}, "end": {}, "extendedProperties": {"private": {}}}]
        with patch("wodplanner.services.calendar_sync.gcal.list_events_in_range", return_value=events):
            result = calendar_sync._rebuild_from_google("token", account, _make_db())
        assert result == {}

    def test_skips_events_with_non_numeric_appointment_id(self):
        account = _make_account()
        events = [
            {
                "id": "ev1",
                "extendedProperties": {"private": {"wodplanner_appointment_id": "not_a_number"}},
            }
        ]
        with patch("wodplanner.services.calendar_sync.gcal.list_events_in_range", return_value=events):
            result = calendar_sync._rebuild_from_google("token", account, _make_db())
        assert result == {}

    def test_returns_empty_on_list_events_exception(self):
        account = _make_account()
        with patch(
            "wodplanner.services.calendar_sync.gcal.list_events_in_range",
            side_effect=Exception("network error"),
        ):
            result = calendar_sync._rebuild_from_google("token", account, _make_db())
        assert result == {}


class TestSyncUser:
    def test_error_when_no_calendar_id(self):
        account = _make_account(calendar_id=None)
        result = calendar_sync.sync_user(account, _make_db(), _make_client(), ENC_KEY, "Alice", "Box")
        assert not result.ok
        assert "no calendar selected" in result.errors[0]

    def test_error_when_token_refresh_fails(self):
        account = _make_account()
        db = _make_db()
        with patch("wodplanner.services.calendar_sync.get_valid_token", side_effect=Exception("token error")):
            result = calendar_sync.sync_user(account, db, _make_client(), ENC_KEY, "Alice", "Box")
        assert not result.ok
        assert "token refresh failed" in result.errors[0]
        db.disable_sync.assert_called_once_with(1, "token refresh failed: token error")

    def test_error_when_wodapp_api_fails(self):
        account = _make_account()
        db = _make_db()
        client = MagicMock()
        client.get_upcoming_reservations.side_effect = Exception("API is down")
        with patch("wodplanner.services.calendar_sync.get_valid_token", return_value="token"):
            result = calendar_sync.sync_user(account, db, client, ENC_KEY, "Alice", "Box")
        assert not result.ok
        assert "WodApp fetch failed" in result.errors[0]

    def test_inserts_new_reservation(self):
        account = _make_account()
        db = _make_db()
        reservation = _make_reservation(appt_id=1, date_start=datetime(2026, 5, 1, 10, 0))
        client = _make_client([reservation])

        with (
            patch("wodplanner.services.calendar_sync.get_valid_token", return_value="token"),
            patch("wodplanner.services.calendar_sync.gcal.insert_event", return_value={"id": "gev1"}),
        ):
            result = calendar_sync.sync_user(account, db, client, ENC_KEY, "Alice", "Box")

        assert result.inserted == 1
        assert result.updated == 0
        assert result.deleted == 0
        assert result.ok

    def test_inserts_reservation_with_date_end(self):
        account = _make_account()
        db = _make_db()
        start = datetime(2026, 5, 1, 10, 0)
        end = datetime(2026, 5, 1, 11, 30)
        reservation = _make_reservation(appt_id=1, date_start=start, date_end=end)
        client = _make_client([reservation])

        with (
            patch("wodplanner.services.calendar_sync.get_valid_token", return_value="token"),
            patch("wodplanner.services.calendar_sync.gcal.insert_event", return_value={"id": "gev1"}),
        ):
            result = calendar_sync.sync_user(account, db, client, ENC_KEY, "Alice", "Box")

        assert result.inserted == 1

    def test_updates_event_when_name_changed(self):
        account = _make_account()
        existing_ev = _make_synced_event(appt_id=1, name="CrossFit")
        db = _make_db(synced_events=[existing_ev])
        # Same appt_id but different name
        reservation = _make_reservation(appt_id=1, name="Gymnastics", date_start=datetime(2026, 5, 1, 10, 0))
        client = _make_client([reservation])

        with (
            patch("wodplanner.services.calendar_sync.get_valid_token", return_value="token"),
            patch("wodplanner.services.calendar_sync.gcal.update_event", return_value={}),
        ):
            result = calendar_sync.sync_user(account, db, client, ENC_KEY, "Alice", "Box")

        assert result.updated == 1
        assert result.inserted == 0

    def test_updates_event_when_start_time_changed(self):
        account = _make_account()
        old_start = datetime(2026, 5, 1, 10, 0)
        new_start = datetime(2026, 5, 1, 11, 0)
        existing_ev = _make_synced_event(appt_id=1, date_start=old_start, name="CrossFit")
        db = _make_db(synced_events=[existing_ev])
        reservation = _make_reservation(appt_id=1, name="CrossFit", date_start=new_start)
        client = _make_client([reservation])

        with (
            patch("wodplanner.services.calendar_sync.get_valid_token", return_value="token"),
            patch("wodplanner.services.calendar_sync.gcal.update_event", return_value={}),
        ):
            result = calendar_sync.sync_user(account, db, client, ENC_KEY, "Alice", "Box")

        assert result.updated == 1

    def test_no_update_when_event_unchanged(self):
        account = _make_account()
        start = datetime(2026, 5, 1, 10, 0)
        existing_ev = _make_synced_event(appt_id=1, date_start=start, name="CrossFit")
        db = _make_db(synced_events=[existing_ev])
        reservation = _make_reservation(appt_id=1, name="CrossFit", date_start=start)
        client = _make_client([reservation])

        with patch("wodplanner.services.calendar_sync.get_valid_token", return_value="token"):
            result = calendar_sync.sync_user(account, db, client, ENC_KEY, "Alice", "Box")

        assert result.updated == 0
        assert result.inserted == 0

    def test_deletes_cancelled_future_event(self):
        account = _make_account()
        future_start = datetime.now() + timedelta(days=3)
        existing_ev = _make_synced_event(appt_id=99, date_start=future_start, name="CrossFit")
        db = _make_db(synced_events=[existing_ev])
        # No matching reservation — appt 99 was cancelled
        client = _make_client([])

        with (
            patch("wodplanner.services.calendar_sync.get_valid_token", return_value="token"),
            patch("wodplanner.services.calendar_sync.gcal.delete_event"),
        ):
            result = calendar_sync.sync_user(account, db, client, ENC_KEY, "Alice", "Box")

        assert result.deleted == 1

    def test_keeps_past_event_even_when_not_in_reservations(self):
        account = _make_account()
        past_start = datetime.now() - timedelta(days=1)
        existing_ev = _make_synced_event(appt_id=99, date_start=past_start, name="CrossFit")
        db = _make_db(synced_events=[existing_ev])
        client = _make_client([])  # Empty — class already happened

        with patch("wodplanner.services.calendar_sync.get_valid_token", return_value="token"):
            result = calendar_sync.sync_user(account, db, client, ENC_KEY, "Alice", "Box")

        assert result.deleted == 0

    def test_triggers_recovery_when_db_empty_but_reservations_exist(self):
        account = _make_account()
        db = _make_db(synced_events=[])
        reservation = _make_reservation(appt_id=1, date_start=datetime(2026, 5, 1, 10, 0))
        client = _make_client([reservation])

        with (
            patch("wodplanner.services.calendar_sync.get_valid_token", return_value="token"),
            patch("wodplanner.services.calendar_sync._rebuild_from_google", return_value={}) as mock_rebuild,
            patch("wodplanner.services.calendar_sync.gcal.insert_event", return_value={"id": "gev1"}),
        ):
            calendar_sync.sync_user(account, db, client, ENC_KEY, "Alice", "Box")

        mock_rebuild.assert_called_once()

    def test_no_recovery_when_db_and_reservations_both_empty(self):
        account = _make_account()
        db = _make_db(synced_events=[])
        client = _make_client([])

        with (
            patch("wodplanner.services.calendar_sync.get_valid_token", return_value="token"),
            patch("wodplanner.services.calendar_sync._rebuild_from_google") as mock_rebuild,
        ):
            calendar_sync.sync_user(account, db, client, ENC_KEY, "Alice", "Box")

        mock_rebuild.assert_not_called()

    def test_insert_error_logged_in_result(self):
        account = _make_account()
        db = _make_db()
        reservation = _make_reservation(appt_id=1, date_start=datetime(2026, 5, 1, 10, 0))
        client = _make_client([reservation])

        with (
            patch("wodplanner.services.calendar_sync.get_valid_token", return_value="token"),
            patch("wodplanner.services.calendar_sync.gcal.insert_event", side_effect=Exception("quota exceeded")),
        ):
            result = calendar_sync.sync_user(account, db, client, ENC_KEY, "Alice", "Box")

        assert not result.ok
        assert "insert appt 1" in result.errors[0]

    def test_sync_status_written_at_end(self):
        account = _make_account()
        db = _make_db()
        client = _make_client([])

        with patch("wodplanner.services.calendar_sync.get_valid_token", return_value="token"):
            calendar_sync.sync_user(account, db, client, ENC_KEY, "Alice", "Box")

        db.update_sync_status.assert_called_once()
        call_args = db.update_sync_status.call_args[0]
        assert call_args[0] == 1  # user_id
        assert call_args[1] == "ok"

    def test_delete_skips_event_with_invalid_date(self):
        account = _make_account()
        ev = SyncedEvent(
            user_id=1,
            id_appointment=99,
            google_event_id="gev99",
            calendar_id="cal_id",
            date_start="not-a-date",
            date_end="not-a-date",
            name="CrossFit",
            etag=None,
            synced_at=datetime.now().isoformat(),
        )
        db = _make_db(synced_events=[ev])
        client = _make_client([])

        with patch("wodplanner.services.calendar_sync.get_valid_token", return_value="token"):
            result = calendar_sync.sync_user(account, db, client, ENC_KEY, "Alice", "Box")

        assert result.deleted == 0
