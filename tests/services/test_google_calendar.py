"""Tests for services/google_calendar.py — Google Calendar API v3 wrapper."""

from unittest.mock import MagicMock, patch

import pytest

from wodplanner.services import google_calendar as gcal


def _mock_resp(json_data, status_code=200):
    mock = MagicMock()
    mock.json.return_value = json_data
    mock.status_code = status_code
    mock.raise_for_status = MagicMock()
    return mock


class TestListCalendars:
    def test_returns_items(self):
        with patch("httpx.get", return_value=_mock_resp({"items": [{"id": "cal1"}]})):
            result = gcal.list_calendars("token")
        assert result == [{"id": "cal1"}]

    def test_returns_empty_list_when_no_items_key(self):
        with patch("httpx.get", return_value=_mock_resp({})):
            result = gcal.list_calendars("token")
        assert result == []

    def test_raises_on_http_error(self):
        mock_resp = _mock_resp({})
        mock_resp.raise_for_status.side_effect = Exception("403")
        with patch("httpx.get", return_value=mock_resp):
            with pytest.raises(Exception, match="403"):
                gcal.list_calendars("bad_token")


class TestCreateCalendar:
    def test_returns_calendar_resource(self):
        cal = {"id": "new_cal_id", "summary": "WodPlanner"}
        with patch("httpx.post", return_value=_mock_resp(cal)):
            result = gcal.create_calendar("token", "WodPlanner")
        assert result["id"] == "new_cal_id"
        assert result["summary"] == "WodPlanner"


class TestInsertEvent:
    def test_returns_created_event(self):
        event = {"id": "ev1", "summary": "CrossFit"}
        with patch("httpx.post", return_value=_mock_resp(event)):
            result = gcal.insert_event("token", "cal_id", {"summary": "CrossFit"})
        assert result["id"] == "ev1"


class TestUpdateEvent:
    def test_returns_updated_event(self):
        event = {"id": "ev1", "summary": "Updated CrossFit"}
        with patch("httpx.put", return_value=_mock_resp(event)):
            result = gcal.update_event("token", "cal_id", "ev1", {"summary": "Updated CrossFit"})
        assert result["summary"] == "Updated CrossFit"


class TestDeleteEvent:
    def test_delete_success_calls_raise_for_status(self):
        mock_resp = _mock_resp({}, status_code=204)
        with patch("httpx.delete", return_value=mock_resp):
            gcal.delete_event("token", "cal_id", "ev1")
        mock_resp.raise_for_status.assert_called_once()

    def test_delete_404_is_silently_ignored(self):
        mock_resp = _mock_resp({}, status_code=404)
        with patch("httpx.delete", return_value=mock_resp):
            gcal.delete_event("token", "cal_id", "ev1")  # Must not raise
        mock_resp.raise_for_status.assert_not_called()

    def test_delete_500_raises(self):
        mock_resp = _mock_resp({}, status_code=500)
        mock_resp.raise_for_status.side_effect = Exception("500 Internal Server Error")
        with patch("httpx.delete", return_value=mock_resp):
            with pytest.raises(Exception, match="500"):
                gcal.delete_event("token", "cal_id", "ev1")


class TestListEventsWithPrivateProperty:
    def test_returns_matching_events(self):
        events = [{"id": "ev1"}, {"id": "ev2"}]
        with patch("httpx.get", return_value=_mock_resp({"items": events})):
            result = gcal.list_events_with_private_property("token", "cal_id", "my_key", "my_value")
        assert result == events

    def test_returns_empty_when_no_items(self):
        with patch("httpx.get", return_value=_mock_resp({})):
            result = gcal.list_events_with_private_property("token", "cal_id", "k", "v")
        assert result == []


class TestListEventsInRange:
    def test_returns_events_in_range(self):
        events = [{"id": "ev1"}, {"id": "ev2"}]
        with patch("httpx.get", return_value=_mock_resp({"items": events})):
            result = gcal.list_events_in_range(
                "token", "cal_id", "2026-01-01T00:00:00Z", "2026-12-31T00:00:00Z"
            )
        assert len(result) == 2

    def test_returns_empty_list_when_no_items(self):
        with patch("httpx.get", return_value=_mock_resp({})):
            result = gcal.list_events_in_range(
                "token", "cal_id", "2026-01-01T00:00:00Z", "2026-12-31T00:00:00Z"
            )
        assert result == []
