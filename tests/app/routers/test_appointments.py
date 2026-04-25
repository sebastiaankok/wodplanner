"""Tests for app/routers/appointments.py."""

from datetime import datetime

from wodplanner.api.client import WodAppError
from wodplanner.models.calendar import (
    AppointmentDetails,
    SubscribeResponse,
    Subscriptions,
    WaitingList,
)


def _details() -> AppointmentDetails:
    return AppointmentDetails(
        id_appointment=1,
        id_appointment_type=10,
        name="CrossFit",
        date_start=datetime(2026, 4, 25, 10, 0),
        date_end=datetime(2026, 4, 25, 11, 0),
        max_subscriptions=20,
        waiting_list=1,
        number_hours_before_subscription_opens=168,
        subscription_open_date="18-04-2026 10:00",
        subscribe_not_opened_yet=0,
        subscribe_closed=0,
        unsubscribe_closed=0,
        subscriptions=Subscriptions(subscribed=1, total=5, full=0, members=[]),
        waitinglist=WaitingList(total=0, members=[]),
    )


class TestGetAppointmentDetails:
    def test_unauthenticated(self, app_client):
        assert app_client.get(
            "/api/appointments/1",
            params={"date_start": "2026-04-25 10:00", "date_end": "2026-04-25 11:00"},
        ).status_code == 401

    def test_success(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.get_appointment_details.return_value = _details()
        app_client.cookies.set("session", session_cookie)
        response = app_client.get(
            "/api/appointments/1",
            params={"date_start": "2026-04-25 10:00", "date_end": "2026-04-25 11:00"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == 1
        assert body["is_subscribed"] is True

    def test_bad_date_format(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.get(
            "/api/appointments/1",
            params={"date_start": "garbage", "date_end": "2026-04-25 11:00"},
        )
        assert response.status_code == 400

    def test_wodapp_error_returns_400(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.get_appointment_details.side_effect = WodAppError("oops")
        app_client.cookies.set("session", session_cookie)
        response = app_client.get(
            "/api/appointments/1",
            params={"date_start": "2026-04-25 10:00", "date_end": "2026-04-25 11:00"},
        )
        assert response.status_code == 400


class TestSubscribe:
    def test_success(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.subscribe.return_value = SubscribeResponse(
            status="OK", notice="Subscribed", subscribedWithSuccess=1
        )
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/api/appointments/1/subscribe",
            json={"date_start": "2026-04-25 10:00", "date_end": "2026-04-25 11:00"},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_bad_date(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/api/appointments/1/subscribe",
            json={"date_start": "garbage", "date_end": "garbage"},
        )
        assert response.status_code == 400

    def test_wodapp_error(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.subscribe.side_effect = WodAppError("full")
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/api/appointments/1/subscribe",
            json={"date_start": "2026-04-25 10:00", "date_end": "2026-04-25 11:00"},
        )
        assert response.status_code == 400


class TestSubscribeWaitingList:
    def test_success(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.subscribe_waitinglist.return_value = SubscribeResponse(
            status="OK", notice="On waitinglist"
        )
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/api/appointments/1/waitinglist",
            json={"date_start": "2026-04-25 10:00", "date_end": "2026-04-25 11:00"},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_bad_date(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/api/appointments/1/waitinglist",
            json={"date_start": "x", "date_end": "x"},
        )
        assert response.status_code == 400

    def test_wodapp_error(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.subscribe_waitinglist.side_effect = WodAppError("err")
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/api/appointments/1/waitinglist",
            json={"date_start": "2026-04-25 10:00", "date_end": "2026-04-25 11:00"},
        )
        assert response.status_code == 400
