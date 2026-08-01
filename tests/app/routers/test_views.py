"""Tests for app/routers/views.py — HTML pages and HTMX endpoints."""

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

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


def _relative_time(dt: datetime) -> str:
    """Test helper — import the private function directly."""
    from wodplanner.app.routers.views import _relative_time as rt
    return rt(dt)


def _similarity_score(exercise: str, suggested: list[str]) -> int:
    from wodplanner.app.routers.views import _similarity_score as ss
    return ss(exercise, suggested)


def _ordered_by_recency(formatted: list[dict], key: str) -> list[str]:
    from wodplanner.app.routers.views import _ordered_by_recency as obr
    return obr(formatted, key)


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
        mock_wodapp_client.get_upcoming_reservations.return_value = ([], {})
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/calendar")
        assert response.status_code == 200

    def test_with_day_param(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.get_day_schedule.return_value = [_appt()]
        mock_wodapp_client.get_upcoming_reservations.return_value = ([], {})
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/calendar?day=2026-04-25")
        assert response.status_code == 200

    def test_reservation_dates_in_template(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.get_day_schedule.return_value = []
        mock_wodapp_client.get_upcoming_reservations.return_value = (
            [
                Reservation(id_appointment=1, name="CrossFit", date_start=datetime(2026, 4, 25, 10, 0)),
                Reservation(id_appointment=2, name="Yoga", date_start=datetime(2026, 4, 27, 9, 0)),
            ],
            {},
        )
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/calendar")
        assert response.status_code == 200
        assert 'data-reservation-dates=' in response.text
        assert '"2026-04-25"' in response.text
        assert '"2026-04-27"' in response.text


class TestCalendarDayPartial:
    def test_partial(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.get_day_schedule.return_value = [_appt()]
        mock_wodapp_client.get_upcoming_reservations.return_value = ([], {})
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/calendar/2026-04-25")
        assert response.status_code == 200

    def test_reservation_dates_in_partial(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.get_day_schedule.return_value = [_appt()]
        mock_wodapp_client.get_upcoming_reservations.return_value = (
            [
                Reservation(id_appointment=1, name="CrossFit", date_start=datetime(2026, 4, 25, 10, 0)),
                Reservation(id_appointment=2, name="Yoga", date_start=datetime(2026, 4, 27, 9, 0)),
            ],
            {},
        )
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/calendar/2026-04-25")
        assert response.status_code == 200
        assert 'data-reservation-dates=' in response.text
        assert '"2026-04-25"' in response.text
        assert '"2026-04-27"' in response.text


class TestToggleFilter:
    def test_toggle_persists(self, app_client, session_cookie, mock_wodapp_client, preferences_service):
        mock_wodapp_client.get_day_schedule.return_value = []
        mock_wodapp_client.get_upcoming_reservations.return_value = ([], {})
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
        mock_wodapp_client.get_upcoming_reservations.return_value = ([], {})
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
        mock_wodapp_client.get_upcoming_reservations.return_value = ([], {})
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/appointments/1/waitinglist",
            data={"date_start": "2026-04-25 10:00", "date_end": "2026-04-25 11:00"},
        )
        assert response.status_code == 200

    def test_unsubscribe(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.unsubscribe.return_value = SubscribeResponse(status="OK")
        mock_wodapp_client.get_day_schedule.return_value = []
        mock_wodapp_client.get_upcoming_reservations.return_value = ([], {})
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
        mock_wodapp_client.get_upcoming_reservations.return_value = ([], {})
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

    def test_edit_form_renders(self, app_client, session_cookie, one_rep_max_service):
        from datetime import date as _date

        entry = one_rep_max_service.add(
            user_id=42, exercise="Back Squat", weight_kg=100, recorded_at=_date(2026, 4, 25)
        )
        app_client.cookies.set("session", session_cookie)
        response = app_client.get(f"/one-rep-maxes/{entry.id}/edit")
        assert response.status_code == 200
        assert "Back Squat" in response.text
        assert "100" in response.text

    def test_edit_form_404(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/one-rep-maxes/99999/edit")
        assert response.status_code == 404

    def test_update(self, app_client, session_cookie, one_rep_max_service):
        from datetime import date as _date

        entry = one_rep_max_service.add(
            user_id=42, exercise="Back Squat", weight_kg=100, recorded_at=_date(2026, 4, 25)
        )
        app_client.cookies.set("session", session_cookie)
        response = app_client.put(
            f"/one-rep-maxes/{entry.id}/edit",
            data={
                "exercise": "Front Squat",
                "weight_kg": "110",
                "recorded_at": "2026-05-01",
            },
        )
        assert response.status_code == 200
        updated = one_rep_max_service.get_by_id(42, entry.id)
        assert updated is not None
        assert updated.exercise == "Front Squat"
        assert updated.weight_kg == 110.0
        assert updated.recorded_at.isoformat() == "2026-05-01"

    def test_update_unknown_exercise_422(self, app_client, session_cookie, one_rep_max_service):
        from datetime import date as _date

        entry = one_rep_max_service.add(
            user_id=42, exercise="Back Squat", weight_kg=100, recorded_at=_date(2026, 4, 25)
        )
        app_client.cookies.set("session", session_cookie)
        response = app_client.put(
            f"/one-rep-maxes/{entry.id}/edit",
            data={
                "exercise": "Unknown Exercise",
                "weight_kg": "110",
                "recorded_at": "2026-05-01",
            },
        )
        assert response.status_code == 422

    def test_update_invalid_weight(self, app_client, session_cookie, one_rep_max_service):
        from datetime import date as _date

        entry = one_rep_max_service.add(
            user_id=42, exercise="Back Squat", weight_kg=100, recorded_at=_date(2026, 4, 25)
        )
        app_client.cookies.set("session", session_cookie)
        response = app_client.put(
            f"/one-rep-maxes/{entry.id}/edit",
            data={
                "exercise": "Back Squat",
                "weight_kg": "9999",
                "recorded_at": "2026-05-01",
            },
        )
        assert response.status_code == 400


class TestBenchmarkModal:
    def test_renders(self, app_client, session_cookie, schedule_service):
        from datetime import date

        schedule_service.add(
            Schedule(date=date(2026, 4, 25), class_type="CrossFit", metcon="Fran for time", gym_id=100)
        )
        app_client.cookies.set("session", session_cookie)
        response = app_client.get(
            "/appointments/1/benchmark",
            params={"date_start": "2026-04-25 10:00", "class_name": "CrossFit"},
        )
        assert response.status_code == 200
        assert "Fran" in response.text

    def test_shows_history(self, app_client, session_cookie, schedule_service, benchmark_service):
        from datetime import date

        schedule_service.add(
            Schedule(date=date(2026, 4, 25), class_type="CrossFit", metcon="Fran", gym_id=100)
        )
        benchmark_service.add_result(
            user_id=42, benchmark_name="Fran", time_seconds=180, is_rx=True, recorded_at="2026-05-05"
        )
        app_client.cookies.set("session", session_cookie)
        response = app_client.get(
            "/appointments/1/benchmark",
            params={"date_start": "2026-04-25 10:00", "class_name": "CrossFit"},
        )
        assert response.status_code == 200
        assert "3:00" in response.text


class TestAddDeleteBenchmarkResult:
    def test_add(self, app_client, session_cookie, benchmark_service):
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/benchmark-results/add",
            data={
                "benchmark_name": "Fran",
                "minutes": "3",
                "seconds": "0",
                "is_rx": "true",
                "recorded_at": "2026-05-05",
            },
        )
        assert response.status_code == 200
        results = benchmark_service.get_results_for_benchmark(42, "Fran")
        assert len(results) == 1
        assert results[0].time_seconds == 180

    def test_add_invalid_time(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/benchmark-results/add",
            data={
                "benchmark_name": "Fran",
                "minutes": "0",
                "seconds": "0",
                "is_rx": "true",
                "recorded_at": "2026-05-05",
            },
        )
        assert response.status_code == 400

    def test_delete(self, app_client, session_cookie, benchmark_service):
        r = benchmark_service.add_result(
            user_id=42, benchmark_name="Fran", time_seconds=180, is_rx=True, recorded_at="2026-05-05"
        )
        app_client.cookies.set("session", session_cookie)
        response = app_client.delete(f"/benchmark-results/{r.id}/delete")
        assert response.status_code == 200
        results = benchmark_service.get_results_for_benchmark(42, "Fran")
        assert len(results) == 0

    def test_edit_form_renders(self, app_client, session_cookie, benchmark_service):
        r = benchmark_service.add_result(
            user_id=42, benchmark_name="Fran", time_seconds=180, is_rx=True, recorded_at="2026-05-05"
        )
        app_client.cookies.set("session", session_cookie)
        response = app_client.get(f"/benchmark-results/{r.id}/edit")
        assert response.status_code == 200
        assert "Fran" in response.text
        assert 'name="minutes"' in response.text
        assert 'name="seconds"' in response.text
        assert "Minutes" in response.text
        assert "Seconds" in response.text
        assert "RX / Scaled" in response.text

    def test_edit_form_404(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/benchmark-results/99999/edit")
        assert response.status_code == 404

    def test_update(self, app_client, session_cookie, benchmark_service):
        r = benchmark_service.add_result(
            user_id=42, benchmark_name="Fran", time_seconds=180, is_rx=True, recorded_at="2026-05-05"
        )
        app_client.cookies.set("session", session_cookie)
        response = app_client.put(
            f"/benchmark-results/{r.id}/edit",
            data={
                "benchmark_name": "Helen",
                "minutes": "4",
                "seconds": "30",
                "is_rx": "false",
                "recorded_at": "2026-06-01",
            },
        )
        assert response.status_code == 200
        result = benchmark_service.get_result(42, r.id)
        assert result is not None
        assert result.benchmark_name == "Helen"
        assert result.time_seconds == 270
        assert result.is_rx is False
        assert result.recorded_at == "2026-06-01"

    def test_update_invalid_time(self, app_client, session_cookie, benchmark_service):
        r = benchmark_service.add_result(
            user_id=42, benchmark_name="Fran", time_seconds=180, is_rx=True, recorded_at="2026-05-05"
        )
        app_client.cookies.set("session", session_cookie)
        response = app_client.put(
            f"/benchmark-results/{r.id}/edit",
            data={
                "benchmark_name": "Fran",
                "minutes": "0",
                "seconds": "0",
                "is_rx": "true",
                "recorded_at": "2026-06-01",
            },
        )
        assert response.status_code == 400


class TestRelativeTime:
    def test_just_now_negative_diff(self):
        dt = datetime.now() + timedelta(seconds=10)
        assert _relative_time(dt) == "just now"

    def test_just_now_seconds(self):
        dt = datetime.now() - timedelta(seconds=30)
        assert _relative_time(dt) == "just now"

    def test_minutes_ago(self):
        dt = datetime.now() - timedelta(minutes=5)
        assert _relative_time(dt) == "5m ago"

    def test_hours_ago(self):
        dt = datetime.now() - timedelta(hours=3)
        assert _relative_time(dt) == "3h ago"

    def test_yesterday(self):
        dt = datetime.now() - timedelta(days=1)
        assert _relative_time(dt) == "yesterday"

    def test_days_ago(self):
        dt = datetime.now() - timedelta(days=10)
        assert _relative_time(dt) == "10d ago"

    def test_months_ago(self):
        dt = datetime.now() - timedelta(days=60)
        assert _relative_time(dt) == "2mo ago"

    def test_years_ago(self):
        dt = datetime.now() - timedelta(days=400)
        assert _relative_time(dt) == "1y ago"

    def test_with_timezone(self):
        from datetime import timezone
        dt = datetime.now(timezone.utc) - timedelta(hours=2)
        result = _relative_time(dt)
        assert result == "2h ago"


class TestSimilarityScore:
    def test_exact_match(self):
        assert _similarity_score("Back Squat", ["Back Squat"]) == 2

    def test_case_insensitive(self):
        assert _similarity_score("back squat", ["Back Squat"]) == 2

    def test_substring_match(self):
        assert _similarity_score("Squat", ["Back Squat"]) == 1

    def test_word_overlap(self):
        assert _similarity_score("Squat Clean", ["Back Squat"]) == 1

    def test_no_match(self):
        assert _similarity_score("Deadlift", ["Back Squat", "Bench Press"]) == 0

    def test_empty_suggested(self):
        assert _similarity_score("Deadlift", []) == 0


class TestOrderedByRecency:
    def test_preserves_order(self):
        entries = [
            {"exercise": "Back Squat", "weight_kg": 100, "recorded_at": "2026-04-01"},
            {"exercise": "Deadlift", "weight_kg": 150, "recorded_at": "2026-04-02"},
            {"exercise": "Back Squat", "weight_kg": 110, "recorded_at": "2026-04-03"},
        ]
        result = _ordered_by_recency(entries, "exercise")
        assert result == ["Back Squat", "Deadlift"]

    def test_empty(self):
        assert _ordered_by_recency([], "exercise") == []


class TestChangelogPage:
    def test_renders(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/changelog")
        assert response.status_code == 200

    def test_file_not_found_fallback(self, app_client, session_cookie):
        with patch("pathlib.Path.read_text", side_effect=FileNotFoundError):
            app_client.cookies.set("session", session_cookie)
            response = app_client.get("/changelog")
        assert response.status_code == 200
        assert "Changelog file not found" in response.text


class TestSettingsPage:
    def test_renders(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/settings")
        assert response.status_code == 200

    def test_shows_tracking_state(self, app_client, session_cookie, preferences_service):
        preferences_service.set_tracking_disabled(42, True)
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/settings")
        assert response.status_code == 200


class TestSettingsToggleFilter:
    def test_toggle_filter(self, app_client, session_cookie, preferences_service):
        preferences_service.set_hidden_class_types(42, ["CrossFit"])
        app_client.cookies.set("session", session_cookie)
        response = app_client.post("/settings/toggle-filter/CrossFit")
        assert response.status_code == 200
        assert "CrossFit" not in preferences_service.get_hidden_class_types(42)

    def test_toggle_filter_hides(self, app_client, session_cookie, preferences_service):
        app_client.cookies.set("session", session_cookie)
        response = app_client.post("/settings/toggle-filter/Gymnastics")
        assert response.status_code == 200
        assert "Gymnastics" in preferences_service.get_hidden_class_types(42)


class TestToggleTracking:
    def test_disable_tracking(self, app_client, session_cookie, preferences_service):
        app_client.cookies.set("session", session_cookie)
        response = app_client.post("/settings/toggle-tracking", data={"enable": "false", "delete_data": "false"})
        assert response.status_code == 200
        assert preferences_service.is_tracking_disabled(42) is True

    def test_enable_tracking(self, app_client, session_cookie, preferences_service):
        preferences_service.set_tracking_disabled(42, True)
        app_client.cookies.set("session", session_cookie)
        response = app_client.post("/settings/toggle-tracking", data={"enable": "true", "delete_data": "false"})
        assert response.status_code == 200
        assert preferences_service.is_tracking_disabled(42) is False

    def test_disable_with_delete(self, app_client, session_cookie, preferences_service):
        app_client.cookies.set("session", session_cookie)
        response = app_client.post("/settings/toggle-tracking", data={"enable": "false", "delete_data": "true"})
        assert response.status_code == 200
        assert preferences_service.is_tracking_disabled(42) is True


class TestDeleteTrackingData:
    def test_delete_data(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.post("/settings/delete-tracking-data")
        assert response.status_code == 200
        assert "Tracking data deleted" in response.text


class TestResetTutorial:
    def test_resets_tooltips(self, app_client, session_cookie, preferences_service):
        preferences_service.dismiss_tooltip(42, "filter")
        app_client.cookies.set("session", session_cookie)
        response = app_client.post("/settings/reset-tutorial")
        assert response.status_code == 200
        assert preferences_service.get_dismissed_tooltips(42) == []


class TestBenchmarkPage:
    def test_renders(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/benchmark")
        assert response.status_code == 200

    def test_shows_entries(self, app_client, session_cookie, benchmark_service):
        benchmark_service.add_result(user_id=42, benchmark_name="Fran", time_seconds=180, is_rx=True, recorded_at="2026-05-05")
        app_client.cookies.set("session", session_cookie)
        response = app_client.get("/benchmark")
        assert response.status_code == 200
        assert "Fran" in response.text


class TestUploadAvatar:
    def test_upload_success(self, app_client, session_cookie, monkeypatch, tmp_path, preferences_service):
        upload_path = tmp_path / "avatars"
        monkeypatch.setattr("wodplanner.app.routers.views._UPLOAD_DIR", upload_path)

        mock_img = MagicMock()
        mock_img.format = "PNG"

        with patch("wodplanner.app.routers.views.Image.open", return_value=mock_img):
            app_client.cookies.set("session", session_cookie)
            response = app_client.post(
                "/avatar/upload",
                files={"avatar": ("test.png", b"fake_image_data", "image/png")},
                follow_redirects=False,
            )
        assert response.status_code == 303
        assert response.headers["location"] == "/friends"
        assert preferences_service.get_avatar_filename(42) == "avatar_42.png"

    def test_upload_invalid_extension(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/avatar/upload",
            files={"avatar": ("test.txt", b"data", "text/plain")},
        )
        assert response.status_code == 400
        assert "Invalid file type" in response.text

    def test_upload_too_large(self, app_client, session_cookie, monkeypatch):
        monkeypatch.setattr("wodplanner.app.routers.views._MAX_UPLOAD_SIZE", 5)
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/avatar/upload",
            files={"avatar": ("test.png", b"x" * 100, "image/png")},
        )
        assert response.status_code == 400
        assert "File too large" in response.text

    def test_upload_invalid_image(self, app_client, session_cookie):
        with patch("wodplanner.app.routers.views.Image.open", side_effect=Exception("corrupt")):
            app_client.cookies.set("session", session_cookie)
            response = app_client.post(
                "/avatar/upload",
                files={"avatar": ("test.png", b"fake", "image/png")},
            )
        assert response.status_code == 400
        assert "Invalid image file" in response.text


class TestOneRepMaxPRCelebration:
    def test_pr_triggers_header(self, app_client, session_cookie, one_rep_max_service):
        from datetime import date as _date
        one_rep_max_service.add(user_id=42, exercise="Back Squat", weight_kg=100, recorded_at=_date(2026, 4, 1))
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/one-rep-maxes/add",
            data={"exercise": "Back Squat", "weight_kg": "120", "recorded_at": "2026-04-25"},
        )
        assert response.status_code == 200
        assert response.headers.get("HX-Trigger") == "pr-celebration"

    def test_non_pr_no_header(self, app_client, session_cookie, one_rep_max_service):
        from datetime import date as _date
        one_rep_max_service.add(user_id=42, exercise="Back Squat", weight_kg=100, recorded_at=_date(2026, 4, 1))
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/one-rep-maxes/add",
            data={"exercise": "Back Squat", "weight_kg": "80", "recorded_at": "2026-04-25"},
        )
        assert response.status_code == 200
        assert "HX-Trigger" not in response.headers or response.headers.get("HX-Trigger") != "pr-celebration"


class TestBenchmarkModalNotFound:
    def test_no_benchmark_detected(self, app_client, session_cookie):
        app_client.cookies.set("session", session_cookie)
        response = app_client.get(
            "/appointments/1/benchmark",
            params={"date_start": "2026-04-25 10:00", "class_name": "RandomClass"},
        )
        assert response.status_code == 404
        assert "No benchmark WOD detected" in response.text


class TestPeopleModalAvatar:
    def test_my_avatar_included(self, app_client, session_cookie, mock_wodapp_client, preferences_service):
        preferences_service.set_avatar_filename(42, "avatar_42.jpg")
        details = _details()
        details.subscriptions.members = [
            Member(id_appuser=1, name="Alice", imageURL=""),
            Member(id_appuser=2, name="Bob", imageURL=""),
        ]
        mock_wodapp_client.get_appointment_details.return_value = details
        app_client.cookies.set("session", session_cookie)
        response = app_client.get(
            "/appointments/1/people",
            params={"date_start": "2026-04-25 10:00", "date_end": "2026-04-25 11:00"},
        )
        assert response.status_code == 200


class TestSubscribeTracking:
    def test_tracking_recorded_on_subscribe(self, app_client, session_cookie, mock_wodapp_client):
        mock_wodapp_client.subscribe.return_value = SubscribeResponse(status="OK", subscribedWithSuccess=1)
        mock_wodapp_client.get_day_schedule.return_value = []
        mock_wodapp_client.get_upcoming_reservations.return_value = ([], {})
        app_client.cookies.set("session", session_cookie)
        response = app_client.post(
            "/appointments/1/subscribe",
            data={
                "date_start": "2026-04-25 10:00",
                "date_end": "2026-04-25 11:00",
                "class_name": "CrossFit",
            },
        )
        assert response.status_code == 200
