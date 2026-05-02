"""Tests for services/calendar_sync.py — full-diff sync engine."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from wodplanner.models.google import GoogleAccount, SyncedEvent
from wodplanner.models.schedule import Schedule
from wodplanner.services import calendar_sync
from wodplanner.services.calendar_sync import CalendarSyncService, SyncResult


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


def _make_service(db=None, schedule_service=None):
    return CalendarSyncService(db or _make_db(), schedule_service)


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


def _make_schedule(warmup=None, strength=None, metcon=None):
    from datetime import date
    return Schedule(
        date=date(2026, 5, 1),
        class_type="CrossFit",
        warmup_mobility=warmup,
        strength_specialty=strength,
        metcon=metcon,
    )


class TestBuildDescription:
    def test_no_schedule_returns_class_name_only(self):
        desc = calendar_sync._build_description("CrossFit", None)
        assert desc == "Class: CrossFit"

    def test_includes_all_schedule_sections(self):
        schedule = _make_schedule(
            warmup="A. Row 500m",
            strength="A. Back Squat 5x3",
            metcon="AMRAP 12: 5 pull-ups",
        )
        desc = calendar_sync._build_description("CrossFit", schedule)
        assert "Class: CrossFit" in desc
        assert "Warmup/Mobility:\nA. Row 500m" in desc
        assert "Strength/Specialty:\nA. Back Squat 5x3" in desc
        assert "Metcon:\nAMRAP 12: 5 pull-ups" in desc

    def test_skips_none_sections(self):
        schedule = _make_schedule(metcon="AMRAP 10: 10 burpees")
        desc = calendar_sync._build_description("CrossFit", schedule)
        assert "Warmup" not in desc
        assert "Strength" not in desc
        assert "Metcon:\nAMRAP 10: 10 burpees" in desc

    def test_sections_separated_by_blank_line(self):
        schedule = _make_schedule(warmup="Warmup stuff", metcon="Metcon stuff")
        desc = calendar_sync._build_description("CrossFit", schedule)
        assert "\n\n" in desc


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

    def test_description_without_schedule(self):
        reservation = _make_reservation(name="CrossFit")
        event = calendar_sync._build_event(reservation, "Gym", "Alice")
        assert event["description"] == "Class: CrossFit"

    def test_description_with_schedule_includes_exercises(self):
        reservation = _make_reservation(name="CrossFit")
        schedule = _make_schedule(metcon="AMRAP 10: 5 pull-ups, 10 push-ups")
        event = calendar_sync._build_event(reservation, "Gym", "Alice", schedule)
        assert "Class: CrossFit" in event["description"]
        assert "AMRAP 10: 5 pull-ups, 10 push-ups" in event["description"]


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
        result = _make_service().sync(account, _make_client(), "Alice", "Box")
        assert not result.ok
        assert "no calendar selected" in result.errors[0]

    def test_error_when_token_refresh_fails(self):
        account = _make_account()
        db = _make_db()
        db.get_valid_token.side_effect = Exception("token error")
        result = _make_service(db).sync(account, _make_client(), "Alice", "Box")
        assert not result.ok
        assert "token refresh failed" in result.errors[0]
        db.disable_sync.assert_called_once_with(1, "token refresh failed: token error")

    def test_error_when_wodapp_api_fails(self):
        account = _make_account()
        db = _make_db()
        db.get_valid_token.return_value = "token"
        client = MagicMock()
        client.get_upcoming_reservations.side_effect = Exception("API is down")
        result = _make_service(db).sync(account, client, "Alice", "Box")
        assert not result.ok
        assert "WodApp fetch failed" in result.errors[0]

    def test_inserts_new_reservation(self):
        account = _make_account()
        db = _make_db()
        db.get_valid_token.return_value = "token"
        reservation = _make_reservation(appt_id=1, date_start=datetime(2026, 5, 1, 10, 0))
        client = _make_client([reservation])

        with patch("wodplanner.services.calendar_sync.gcal.insert_event", return_value={"id": "gev1"}):
            result = _make_service(db).sync(account, client, "Alice", "Box")

        assert result.inserted == 1
        assert result.updated == 0
        assert result.deleted == 0
        assert result.ok

    def test_inserts_reservation_with_date_end(self):
        account = _make_account()
        db = _make_db()
        db.get_valid_token.return_value = "token"
        start = datetime(2026, 5, 1, 10, 0)
        end = datetime(2026, 5, 1, 11, 30)
        reservation = _make_reservation(appt_id=1, date_start=start, date_end=end)
        client = _make_client([reservation])

        with patch("wodplanner.services.calendar_sync.gcal.insert_event", return_value={"id": "gev1"}):
            result = _make_service(db).sync(account, client, "Alice", "Box")

        assert result.inserted == 1

    def test_updates_event_when_name_changed(self):
        account = _make_account()
        existing_ev = _make_synced_event(appt_id=1, name="CrossFit")
        db = _make_db(synced_events=[existing_ev])
        db.get_valid_token.return_value = "token"
        reservation = _make_reservation(appt_id=1, name="Gymnastics", date_start=datetime(2026, 5, 1, 10, 0))
        client = _make_client([reservation])

        with patch("wodplanner.services.calendar_sync.gcal.update_event", return_value={}):
            result = _make_service(db).sync(account, client, "Alice", "Box")

        assert result.updated == 1
        assert result.inserted == 0

    def test_updates_event_when_start_time_changed(self):
        account = _make_account()
        old_start = datetime(2026, 5, 1, 10, 0)
        new_start = datetime(2026, 5, 1, 11, 0)
        existing_ev = _make_synced_event(appt_id=1, date_start=old_start, name="CrossFit")
        db = _make_db(synced_events=[existing_ev])
        db.get_valid_token.return_value = "token"
        reservation = _make_reservation(appt_id=1, name="CrossFit", date_start=new_start)
        client = _make_client([reservation])

        with patch("wodplanner.services.calendar_sync.gcal.update_event", return_value={}):
            result = _make_service(db).sync(account, client, "Alice", "Box")

        assert result.updated == 1

    def test_no_update_when_event_unchanged(self):
        account = _make_account()
        start = datetime(2026, 5, 1, 10, 0)
        existing_ev = _make_synced_event(appt_id=1, date_start=start, name="CrossFit")
        db = _make_db(synced_events=[existing_ev])
        db.get_valid_token.return_value = "token"
        reservation = _make_reservation(appt_id=1, name="CrossFit", date_start=start)
        client = _make_client([reservation])

        result = _make_service(db).sync(account, client, "Alice", "Box")

        assert result.updated == 0
        assert result.inserted == 0

    def test_deletes_cancelled_future_event(self):
        account = _make_account()
        future_start = datetime.now() + timedelta(days=3)
        existing_ev = _make_synced_event(appt_id=99, date_start=future_start, name="CrossFit")
        db = _make_db(synced_events=[existing_ev])
        db.get_valid_token.return_value = "token"
        client = _make_client([])

        with patch("wodplanner.services.calendar_sync.gcal.delete_event"):
            result = _make_service(db).sync(account, client, "Alice", "Box")

        assert result.deleted == 1

    def test_keeps_past_event_even_when_not_in_reservations(self):
        account = _make_account()
        past_start = datetime.now() - timedelta(days=1)
        existing_ev = _make_synced_event(appt_id=99, date_start=past_start, name="CrossFit")
        db = _make_db(synced_events=[existing_ev])
        db.get_valid_token.return_value = "token"
        client = _make_client([])

        result = _make_service(db).sync(account, client, "Alice", "Box")

        assert result.deleted == 0

    def test_triggers_recovery_when_db_empty_but_reservations_exist(self):
        account = _make_account()
        db = _make_db(synced_events=[])
        db.get_valid_token.return_value = "token"
        reservation = _make_reservation(appt_id=1, date_start=datetime(2026, 5, 1, 10, 0))
        client = _make_client([reservation])

        with (
            patch("wodplanner.services.calendar_sync._rebuild_from_google", return_value={}) as mock_rebuild,
            patch("wodplanner.services.calendar_sync.gcal.insert_event", return_value={"id": "gev1"}),
        ):
            _make_service(db).sync(account, client, "Alice", "Box")

        mock_rebuild.assert_called_once()

    def test_no_recovery_when_db_and_reservations_both_empty(self):
        account = _make_account()
        db = _make_db(synced_events=[])
        db.get_valid_token.return_value = "token"
        client = _make_client([])

        with patch("wodplanner.services.calendar_sync._rebuild_from_google") as mock_rebuild:
            _make_service(db).sync(account, client, "Alice", "Box")

        mock_rebuild.assert_not_called()

    def test_insert_error_logged_in_result(self):
        account = _make_account()
        db = _make_db()
        db.get_valid_token.return_value = "token"
        reservation = _make_reservation(appt_id=1, date_start=datetime(2026, 5, 1, 10, 0))
        client = _make_client([reservation])

        with patch("wodplanner.services.calendar_sync.gcal.insert_event", side_effect=Exception("quota exceeded")):
            result = _make_service(db).sync(account, client, "Alice", "Box")

        assert not result.ok
        assert "insert appt 1" in result.errors[0]

    def test_sync_status_written_at_end(self):
        account = _make_account()
        db = _make_db()
        db.get_valid_token.return_value = "token"
        client = _make_client([])

        _make_service(db).sync(account, client, "Alice", "Box")

        db.update_sync_status.assert_called_once()
        call_args = db.update_sync_status.call_args[0]
        assert call_args[0] == 1  # user_id
        assert call_args[1] == "ok"

    def test_inserts_with_schedule_exercises_in_description(self):
        account = _make_account()
        db = _make_db()
        db.get_valid_token.return_value = "token"
        reservation = _make_reservation(appt_id=1, name="CrossFit", date_start=datetime(2026, 5, 1, 10, 0))
        client = _make_client([reservation])
        schedule = _make_schedule(metcon="AMRAP 10: 5 pull-ups")
        schedule_service = MagicMock()
        schedule_service.find_for_appointment.return_value = schedule
        inserted_events = []

        def capture_insert(token, cal_id, event_body):
            inserted_events.append(event_body)
            return {"id": "gev1"}

        with patch("wodplanner.services.calendar_sync.gcal.insert_event", side_effect=capture_insert):
            result = _make_service(db, schedule_service).sync(account, client, "Alice", "Box", gym_id=42)

        assert result.inserted == 1
        assert "AMRAP 10: 5 pull-ups" in inserted_events[0]["description"]
        schedule_service.find_for_appointment.assert_called_once_with("CrossFit", datetime(2026, 5, 1, 10, 0).date(), gym_id=42)

    def test_inserts_without_schedule_when_none_provided(self):
        account = _make_account()
        db = _make_db()
        db.get_valid_token.return_value = "token"
        reservation = _make_reservation(appt_id=1, name="CrossFit", date_start=datetime(2026, 5, 1, 10, 0))
        client = _make_client([reservation])
        inserted_events = []

        def capture_insert(token, cal_id, event_body):
            inserted_events.append(event_body)
            return {"id": "gev1"}

        with patch("wodplanner.services.calendar_sync.gcal.insert_event", side_effect=capture_insert):
            result = _make_service(db).sync(account, client, "Alice", "Box")

        assert result.inserted == 1
        assert inserted_events[0]["description"] == "Class: CrossFit"

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
        db.get_valid_token.return_value = "token"
        client = _make_client([])

        result = _make_service(db).sync(account, client, "Alice", "Box")

        assert result.deleted == 0
