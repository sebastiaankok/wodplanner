"""Tests for app/routers/views.py — HTML pages and HTMX endpoints."""

from datetime import date, datetime

from wodplanner.models.calendar import (
    Appointment,
    AppointmentDetails,
    Member,
    Reservation,
    SubscribeResponse,
    Subscriptions,
    WaitingList,
)
from wodplanner.models.schedule import Schedule


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
        subscriptions=Subscriptions(
            subscribed=0,
            total=2,
            full=0,
            members=[Member(id_appuser=1, name="Alice", imageURL="")],
        ),
        waitinglist=WaitingList(total=0, members=[]),
    )


class TestLoginPage:
    def test_renders_when_unauthenticated(self, app_client):
        response = app_client.get("/login")
        assert response.status_code == 200
        assert "<form" in response.text.lower()

    def test_redirects_when_authenticated(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/login", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/"

    def test_error_param_passed(self, app_client):
        response = app_client.get("/login?error=Bad+credentials")
        assert response.status_code == 200


class TestHomePage:
    def test_unauth_redirects(self, app_client):
        response = app_client.get("/", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"

    def test_authenticated_renders(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.get_upcoming_reservations.return_value = (
            [
                Reservation(
                    id_appointment=1,
                    name="CrossFit",
                    date_start=datetime(2026, 4, 25, 10, 0),
                )
            ],
            {"logo": "logo.png"},
        )
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/")
        assert response.status_code == 200


class TestCalendarPage:
    def test_renders(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.get_day_schedule.return_value = []
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/calendar")
        assert response.status_code == 200

    def test_with_day_param(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.get_day_schedule.return_value = [_appt()]
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/calendar?day=2026-04-25")
        assert response.status_code == 200


class TestCalendarDayPartial:
    def test_partial(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.get_day_schedule.return_value = [_appt()]
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/calendar/2026-04-25")
        assert response.status_code == 200


class TestToggleFilter:
    def test_toggle_persists(self, app_client, session_cookie, mock_wodapp_client, preferences_service):
        mock_wodapp_client.get_day_schedule.return_value = []
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/filters/toggle/CrossFit", data={"current_date": "2026-04-25"}
        )
        assert response.status_code == 200
        assert "CrossFit" in preferences_service.get_hidden_class_types(42)


class TestDismissTooltip:
    def test_dismiss(self, app_client, session_cookie, preferences_service):
        app_client.cookies.set("session", session_cookie)
        response = app_client.post("/tooltips/dismiss/filter")
        assert response.status_code == 200
        assert "filter" in preferences_service.get_dismissed_tooltips(42)


class TestOneRepMaxPage:
    def test_renders(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/1rm")
        assert response.status_code == 200


class TestFriendsPage:
    def test_renders_empty(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/friends")
        assert response.status_code == 200

    def test_renders_with_friends(self, app_client, session_cookie, friends_service):
        friends_service.add(owner_user_id=42, appuser_id=1, name="Alice")
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/friends")
        assert response.status_code == 200
        assert "Alice" in response.text


class TestAddDeleteFriendView:
    def test_add(self, app_client, session_cookie, friends_service):
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/friends/add", data={"appuser_id": "10", "name": "Bob"}
        )
        assert response.status_code == 200
        assert friends_service.get_by_appuser_id(42, 10) is not None

    def test_delete(self, app_client, session_cookie, friends_service):
        f = friends_service.add(owner_user_id=42, appuser_id=11, name="Carol")
        app_client.cookies.set("session", session_cookie)
        response = app_client.delete(f"/friends/{f.id}/delete")
        assert response.status_code == 200
        assert friends_service.get(42, f.id) is None


class TestSubscribeUnsubscribeViews:
    def test_subscribe(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.subscribe.return_value = SubscribeResponse(
            status="OK", subscribedWithSuccess=1
        )
        mock_wodapp_client.get_day_schedule.return_value = []
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/appointments/1/subscribe",
            data={"date_start": "2026-04-25 10:00", "date_end": "2026-04-25 11:00"},
        )
        assert response.status_code == 200
        mock_wodapp_client.subscribe.assert_called_once()

    def test_waitinglist(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.subscribe_waitinglist.return_value = SubscribeResponse(
            status="OK"
        )
        mock_wodapp_client.get_day_schedule.return_value = []
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/appointments/1/waitinglist",
            data={"date_start": "2026-04-25 10:00", "date_end": "2026-04-25 11:00"},
        )
        assert response.status_code == 200

    def test_unsubscribe(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.unsubscribe.return_value = SubscribeResponse(status="OK")
        mock_wodapp_client.get_day_schedule.return_value = []
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/appointments/1/unsubscribe",
            data={
                "date_start": "2026-04-25 10:00",
                "date_end": "2026-04-25 11:00",
                "is_waitinglist": "false",
            },
        )
        assert response.status_code == 200
        mock_wodapp_client.unsubscribe.assert_called_once()

    def test_unsubscribe_waitinglist(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.unsubscribe_waitinglist.return_value = SubscribeResponse(status="OK")
        mock_wodapp_client.get_day_schedule.return_value = []
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/appointments/1/unsubscribe",
            data={
                "date_start": "2026-04-25 10:00",
                "date_end": "2026-04-25 11:00",
                "is_waitinglist": "true",
            },
        )
        assert response.status_code == 200
        mock_wodapp_client.unsubscribe_waitinglist.assert_called_once()


class TestPeopleModal:
    def test_renders(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.get_appointment_details.return_value = _details()
        app_client.cookies.set("session", session_cookie)
        response = app_client.get(
            "/appointments/1/people",
            params={"date_start": "2026-04-25 10:00", "date_end": "2026-04-25 11:00"},
        )
        assert response.status_code == 200
        assert "Alice" in response.text

    def test_self_discovery_via_name_match(self, app_client, mock_wodapp_client, preferences_service):
        # session firstname "User" matches one member exactly → should set my_appuser_id
        from wodplanner.app.config import settings
        from wodplanner.models.auth import AuthSession
        from wodplanner.services import session as cookie_session

        session = AuthSession(
            token="t",
            user_id=77,
            appuser_id=None,  # force discovery path
            username="u",
            firstname="User",
            gym_id=10,
            gym_name="G",
        )
        cookie = cookie_session.encode(session, settings.secret_key)

        details = _details()
        details.subscriptions.members = [Member(id_appuser=8888, name="User", imageURL="")]
        mock_wodapp_client.get_appointment_details.return_value = details

        app_client.cookies.set("session", cookie)
        response = app_client.get(
            "/appointments/1/people",
            params={"date_start": "2026-04-25 10:00", "date_end": "2026-04-25 11:00"},
        )
        assert response.status_code == 200
        assert preferences_service.get_my_appuser_id(77) == 8888


class TestAddFriendFromPeople:
    def test_adds_and_returns_modal(self, app_client, session_cookie, mock_wodapp_client, friends_service):
        mock_wodapp_client.get_appointment_details.return_value = _details()
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/friends/add-from-people",
            data={
                "appuser_id": "1",
                "name": "Alice",
                "appointment_id": "1",
                "date_start": "2026-04-25 10:00",
                "date_end": "2026-04-25 11:00",
            },
        )
        assert response.status_code == 200
        assert friends_service.get_by_appuser_id(42, 1) is not None


class TestScheduleModal:
    def test_renders(self, app_client, session_cookie, schedule_service):
        schedule_service.add(
            Schedule(date=date(2026, 4, 25), class_type="CrossFit", metcon="m", gym_id=100)
        )
        app_client.cookies.set("session", session_cookie)
        response = app_client.get(
            "/appointments/1/schedule",
            params={"date_start": "2026-04-25 10:00", "class_name": "CrossFit"},
        )
        assert response.status_code == 200


class TestOneRepMaxModal:
    def test_renders_no_schedule(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.get(
            "/appointments/1/1rm",
            params={"date_start": "2026-04-25 10:00", "class_name": "CrossFit"},
        )
        assert response.status_code == 200

    def test_renders_with_schedule_suggestions(
        self, app_client, session_cookie, schedule_service
    ):
        schedule_service.add(
            Schedule(
                date=date(2026, 4, 25),
                class_type="CrossFit",
                strength_specialty="1rm Back Squat",
                metcon="",
                gym_id=100,
            )
        )
        app_client.cookies.set("session", session_cookie)
        response = app_client.get(
            "/appointments/1/1rm",
            params={"date_start": "2026-04-25 10:00", "class_name": "CrossFit"},
        )
        assert response.status_code == 200


class TestAddDeleteOneRepMax:
    def test_add(self, app_client, session_cookie, one_rep_max_service):
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/one-rep-maxes/add",
            data={
                "exercise": "Back Squat",
                "weight_kg": "100",
                "recorded_at": "2026-04-25",
            },
        )
        assert response.status_code == 200
        assert len(one_rep_max_service.get_all(42)) == 1

    def test_add_unknown_exercise_422(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/one-rep-maxes/add",
            data={
                "exercise": "Unknown Exercise",
                "weight_kg": "100",
                "recorded_at": "2026-04-25",
            },
        )
        assert response.status_code == 422

    def test_add_invalid_weight(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/one-rep-maxes/add",
            data={
                "exercise": "Back Squat",
                "weight_kg": "9999",
                "recorded_at": "2026-04-25",
            },
        )
        assert response.status_code == 400

    def test_add_invalid_date(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/one-rep-maxes/add",
            data={
                "exercise": "Back Squat",
                "weight_kg": "100",
                "recorded_at": "garbage",
            },
        )
        assert response.status_code == 400

    def test_delete(self, app_client, session_cookie, one_rep_max_service):
        from datetime import date as _date

        entry = one_rep_max_service.add(
            user_id=42, exercise="Back Squat", weight_kg=100, recorded_at=_date(2026, 4, 25)
        )
        app_client.cookies.set("session", session_cookie)
        response = app_client.delete(f"/one-rep-maxes/{entry.id}/delete")
        assert response.status_code == 200
