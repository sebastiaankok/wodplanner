"""Tests for app/routers/calendar.py."""

from datetime import datetime

from wodplanner.models.calendar import Appointment, Member, WaitingList


def _appt(id_=1) -> Appointment:
    return Appointment(
        id_appointment=id_,
        id_appointment_type=10,
        id_parent=None,
        name="CrossFit",
        date_start=datetime(2026, 4, 25, 10, 0),
        date_end=datetime(2026, 4, 25, 11, 0),
        max_subscriptions=20,
        total_subscriptions=5,
        status="open",
    )


class TestDaySchedule:
    def test_unauthenticated(self, app_client):
        assert app_client.get("/api/calendar/day").status_code == 401

    def test_default_today(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.get_day_schedule.return_value = [_appt()]
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/api/calendar/day")
        assert response.status_code == 200
        body = response.json()
        assert len(body["appointments"]) == 1
        assert body["appointments"][0]["id"] == 1

    def test_specific_day_no_friends(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.get_day_schedule.return_value = [_appt()]
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/api/calendar/day", params={"day": "2026-04-25"})
        assert response.status_code == 200
        assert response.json()["date"] == "2026-04-25"

    def test_include_friends_with_match(self, app_client, session_cookie, mock_wodapp_client, friends_service):
        friends_service.add(owner_user_id=42, appuser_id=999, name="BFF")
        mock_wodapp_client.get_day_schedule.return_value = [_appt()]
        mock_wodapp_client.get_appointment_members.return_value = (
            [Member(id_appuser=999, name="BFF", imageURL="")],
            WaitingList(total=0, members=[]),
        )
        app_client.cookies.set("session", session_cookie)
        response = app_client.get(
            "/api/calendar/day",
            params={"day": "2026-04-25", "include_friends": True},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["appointments"][0]["friends"][0]["id"] == 999

    def test_include_friends_swallows_exception(
        self, app_client, session_cookie, mock_wodapp_client, friends_service
    ):
        friends_service.add(owner_user_id=42, appuser_id=999, name="BFF")
        mock_wodapp_client.get_day_schedule.return_value = [_appt()]
        mock_wodapp_client.get_appointment_members.side_effect = RuntimeError("boom")
        app_client.cookies.set("session", session_cookie)
        response = app_client.get(
            "/api/calendar/day",
            params={"day": "2026-04-25", "include_friends": True},
        )
        assert response.status_code == 200
        assert response.json()["appointments"][0]["friends"] == []


class TestWeekSchedule:
    def test_default(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.get_day_schedule.return_value = []
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/api/calendar/week", params={"start_date": "2026-04-25"})
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 7

    def test_include_friends_swallows_exception(
        self, app_client, session_cookie, mock_wodapp_client, friends_service
    ):
        friends_service.add(owner_user_id=42, appuser_id=999, name="BFF")
        mock_wodapp_client.get_day_schedule.return_value = [_appt()]
        mock_wodapp_client.get_appointment_members.side_effect = RuntimeError("boom")
        app_client.cookies.set("session", session_cookie)
        response = app_client.get(
            "/api/calendar/week",
            params={"start_date": "2026-04-25", "include_friends": True},
        )
        assert response.status_code == 200
        body = response.json()
        assert all(d["appointments"][0]["friends"] == [] for d in body if d["appointments"])

    def test_include_friends_with_match(
        self, app_client, session_cookie, mock_wodapp_client, friends_service
    ):
        friends_service.add(owner_user_id=42, appuser_id=999, name="BFF")
        mock_wodapp_client.get_day_schedule.return_value = [_appt()]
        mock_wodapp_client.get_appointment_members.return_value = (
            [Member(id_appuser=999, name="MemberName", imageURL="")],
            WaitingList(total=0, members=[]),
        )
        app_client.cookies.set("session", session_cookie)
        response = app_client.get(
            "/api/calendar/week",
            params={"start_date": "2026-04-25", "include_friends": True},
        )
        assert response.status_code == 200
        body = response.json()
        # At least one day should have a matched friend
        assert any(
            day["appointments"] and day["appointments"][0]["friends"] for day in body
        )
