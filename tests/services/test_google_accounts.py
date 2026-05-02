"""Tests for services/google_accounts.py — DB service for Google Calendar sync state."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from wodplanner.models.google import GoogleAccount
from wodplanner.services.google_accounts import GoogleAccountsService

ENC_KEY = b"A" * 44  # Placeholder — crypto is mocked


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


@pytest.fixture
def svc(db_path):
    return GoogleAccountsService(db_path, ENC_KEY)


def _insert_account(svc, user_id=1):
    return svc.upsert_account(
        user_id=user_id,
        google_email="user@gmail.com",
        access_token="enc_access",
        refresh_token="enc_refresh",
        token_expiry=None,
        scopes="calendar",
    )


class TestGetAccount:
    def test_returns_none_when_not_found(self, svc):
        assert svc.get_account(999) is None

    def test_returns_account_after_upsert(self, svc):
        _insert_account(svc)
        account = svc.get_account(1)
        assert account is not None
        assert account.google_email == "user@gmail.com"
        assert account.user_id == 1


class TestUpsertAccount:
    def test_inserts_new_account(self, svc):
        account = _insert_account(svc)
        assert account.user_id == 1
        assert account.sync_enabled is False

    def test_updates_existing_account(self, svc):
        _insert_account(svc)
        svc.upsert_account(1, "new@gmail.com", "enc2", "enc_ref2", None, "calendar")
        account = svc.get_account(1)
        assert account.google_email == "new@gmail.com"

    def test_multiple_users(self, svc):
        _insert_account(svc, user_id=1)
        _insert_account(svc, user_id=2)
        assert svc.get_account(1) is not None
        assert svc.get_account(2) is not None


class TestUpdateCalendar:
    def test_sets_calendar_id_and_enables_sync(self, svc):
        _insert_account(svc)
        result = svc.update_calendar(1, "cal_id_123", "My Calendar")
        assert result is True
        account = svc.get_account(1)
        assert account.calendar_id == "cal_id_123"
        assert account.calendar_summary == "My Calendar"
        assert account.sync_enabled is True

    def test_returns_false_for_unknown_user(self, svc):
        result = svc.update_calendar(999, "cal_id", "name")
        assert result is False


class TestUpdateTokens:
    def test_updates_access_token_and_expiry(self, svc):
        _insert_account(svc)
        svc.update_tokens(1, "new_enc_token", "2026-12-31T00:00:00")
        account = svc.get_account(1)
        assert account.access_token == "new_enc_token"
        assert account.token_expiry == "2026-12-31T00:00:00"

    def test_clears_expiry_when_none(self, svc):
        _insert_account(svc)
        svc.update_tokens(1, "tok", None)
        account = svc.get_account(1)
        assert account.token_expiry is None


class TestUpdateSyncStatus:
    def test_sets_status_and_timestamp(self, svc):
        _insert_account(svc)
        svc.update_sync_status(1, "ok")
        account = svc.get_account(1)
        assert account.last_sync_status == "ok"
        assert account.last_sync_at is not None

    def test_updates_status_multiple_times(self, svc):
        _insert_account(svc)
        svc.update_sync_status(1, "ok")
        svc.update_sync_status(1, "error: something failed")
        account = svc.get_account(1)
        assert account.last_sync_status == "error: something failed"


class TestDisableSync:
    def test_disables_sync_and_sets_reason(self, svc):
        _insert_account(svc)
        svc.update_calendar(1, "cal_id", "cal")
        assert svc.get_account(1).sync_enabled is True
        svc.disable_sync(1, "token expired")
        account = svc.get_account(1)
        assert account.sync_enabled is False
        assert account.last_sync_status == "token expired"


class TestDeleteAccount:
    def test_removes_account(self, svc):
        _insert_account(svc)
        svc.delete_account(1)
        assert svc.get_account(1) is None

    def test_also_removes_synced_events(self, svc):
        _insert_account(svc)
        svc.upsert_synced_event(
            1, 101, "gev1", "cal_id",
            "2026-04-27T10:00:00", "2026-04-27T11:00:00", "CrossFit"
        )
        svc.delete_account(1)
        assert svc.get_synced_events(1) == []

    def test_no_error_when_account_does_not_exist(self, svc):
        svc.delete_account(999)  # Must not raise


class TestGetAllSyncEnabledUserIds:
    def test_returns_users_with_sync_calendar_and_session(self, svc):
        _insert_account(svc, user_id=1)
        svc.update_calendar(1, "cal_id", "cal")
        svc.store_wodapp_session_enc(1, "enc_session")
        ids = svc.get_all_sync_enabled_user_ids()
        assert 1 in ids

    def test_excludes_users_without_sync_enabled(self, svc):
        _insert_account(svc, user_id=2)
        # Not calling update_calendar — sync_enabled stays False
        ids = svc.get_all_sync_enabled_user_ids()
        assert 2 not in ids

    def test_excludes_users_without_wodapp_session(self, svc):
        _insert_account(svc, user_id=3)
        svc.update_calendar(3, "cal_id", "cal")
        # sync_enabled=True but no session stored
        ids = svc.get_all_sync_enabled_user_ids()
        assert 3 not in ids

    def test_returns_empty_when_none_qualify(self, svc):
        assert svc.get_all_sync_enabled_user_ids() == []


class TestWodappSessionEnc:
    def test_store_and_retrieve(self, svc):
        _insert_account(svc)
        svc.store_wodapp_session_enc(1, "enc_session_data")
        result = svc.get_wodapp_session_enc(1)
        assert result == "enc_session_data"

    def test_returns_none_when_not_stored(self, svc):
        _insert_account(svc)
        assert svc.get_wodapp_session_enc(1) is None

    def test_returns_none_for_unknown_user(self, svc):
        assert svc.get_wodapp_session_enc(999) is None

    def test_overwrites_existing_session(self, svc):
        _insert_account(svc)
        svc.store_wodapp_session_enc(1, "old_session")
        svc.store_wodapp_session_enc(1, "new_session")
        assert svc.get_wodapp_session_enc(1) == "new_session"


class TestSyncedEvents:
    def test_upsert_and_get(self, svc):
        _insert_account(svc)
        svc.upsert_synced_event(
            1, 101, "gev1", "cal_id",
            "2026-04-27T10:00:00", "2026-04-27T11:00:00", "CrossFit", etag="etag1"
        )
        events = svc.get_synced_events(1)
        assert len(events) == 1
        assert events[0].id_appointment == 101
        assert events[0].google_event_id == "gev1"
        assert events[0].etag == "etag1"

    def test_upsert_updates_existing_event(self, svc):
        _insert_account(svc)
        svc.upsert_synced_event(
            1, 101, "gev1", "cal_id",
            "2026-04-27T10:00:00", "2026-04-27T11:00:00", "CrossFit"
        )
        svc.upsert_synced_event(
            1, 101, "gev1_updated", "cal_id",
            "2026-04-28T10:00:00", "2026-04-28T11:00:00", "Gymnastics"
        )
        events = svc.get_synced_events(1)
        assert len(events) == 1
        assert events[0].google_event_id == "gev1_updated"
        assert events[0].name == "Gymnastics"

    def test_delete_synced_event(self, svc):
        _insert_account(svc)
        svc.upsert_synced_event(
            1, 101, "gev1", "cal_id",
            "2026-04-27T10:00:00", "2026-04-27T11:00:00", "CrossFit"
        )
        svc.delete_synced_event(1, 101)
        assert svc.get_synced_events(1) == []

    def test_get_synced_events_empty_for_new_user(self, svc):
        _insert_account(svc)
        assert svc.get_synced_events(1) == []

    def test_multiple_events_for_same_user(self, svc):
        _insert_account(svc)
        svc.upsert_synced_event(
            1, 101, "gev1", "cal_id",
            "2026-04-27T10:00:00", "2026-04-27T11:00:00", "CrossFit"
        )
        svc.upsert_synced_event(
            1, 102, "gev2", "cal_id",
            "2026-04-28T10:00:00", "2026-04-28T11:00:00", "Gymnastics"
        )
        events = svc.get_synced_events(1)
        assert len(events) == 2


class TestGetValidToken:
    def test_returns_decrypted_token_when_no_expiry(self, svc):
        _insert_account(svc)
        account = svc.get_account(1)
        with patch("wodplanner.services.google_accounts.crypto.decrypt", return_value="raw_token"):
            token = svc.get_valid_token(account)
        assert token == "raw_token"

    def test_returns_decrypted_token_when_expiry_is_far_future(self, svc):
        _insert_account(svc)
        far_future = (datetime.now() + timedelta(hours=2)).isoformat()
        svc.update_tokens(1, "enc_access", far_future)
        account = svc.get_account(1)
        with patch("wodplanner.services.google_accounts.crypto.decrypt", return_value="raw_token"):
            token = svc.get_valid_token(account)
        assert token == "raw_token"

    def test_refreshes_when_token_near_expiry(self, svc):
        _insert_account(svc)
        near_expiry = (datetime.now() + timedelta(minutes=2)).isoformat()
        svc.update_tokens(1, "enc_access", near_expiry)
        account = svc.get_account(1)
        with (
            patch("wodplanner.services.google_accounts.crypto.decrypt", side_effect=["enc_access", "enc_refresh"]),
            patch("wodplanner.services.google_accounts.refresh_access_token", return_value=("new_tok", "new_expiry")),
            patch("wodplanner.services.google_accounts.crypto.encrypt", return_value="enc_new_tok"),
        ):
            token = svc.get_valid_token(account)
        assert token == "new_tok"

    def test_no_refresh_when_not_near_expiry(self, svc):
        _insert_account(svc)
        far_future = (datetime.now() + timedelta(hours=2)).isoformat()
        svc.update_tokens(1, "enc_access", far_future)
        account = svc.get_account(1)
        call_count = [0]
        original = svc.update_tokens
        svc.update_tokens = lambda *a, **kw: (call_count.__setitem__(0, call_count[0] + 1), original(*a, **kw))
        with patch("wodplanner.services.google_accounts.crypto.decrypt", return_value="raw_token"):
            svc.get_valid_token(account)
        assert call_count[0] == 0
