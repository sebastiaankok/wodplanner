from datetime import date, datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest

from wodplanner.api.client import (
    AuthenticationError,
    WodAppClient,
    WodAppError,
)
from wodplanner.models.auth import AuthSession
from wodplanner.models.calendar import Member, WaitingList
from wodplanner.services.api_cache import ApiCacheService


class MockResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=MagicMock(), response=self
            )


class TestWodAppClientLogin:
    @patch("wodplanner.api.client.httpx.Client")
    def test_login_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.post.return_value = MockResponse({
            "status": "OK",
            "id_user": 123,
            "username": "test@example.com",
            "firstname": "Test",
            "token": "test_token",
            "gyms": [{"id_gym": 1, "idc": 1, "name": "Test Gym", "city": "Test City"}],
        })

        client = WodAppClient()
        session = client.login("user", "pass")

        assert session.token == "test_token"
        assert session.user_id == 123
        assert session.gym_id == 1

    @patch("wodplanner.api.client.httpx.Client")
    def test_login_no_gyms_raises_auth_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.post.return_value = MockResponse({
            "status": "OK",
            "id_user": 123,
            "username": "test@example.com",
            "firstname": "Test",
            "token": "test_token",
            "gyms": [],
        })

        client = WodAppClient()
        with pytest.raises(AuthenticationError, match="No gyms"):
            client.login("user", "pass")

    @patch("wodplanner.api.client.httpx.Client")
    def test_login_api_error_raises(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.post.return_value = MockResponse({
            "status": "ERROR",
            "notice": "Invalid credentials",
        })

        client = WodAppClient()
        with pytest.raises(WodAppError, match="API error"):
            client.login("user", "pass")

    @patch("wodplanner.api.client.httpx.Client")
    def test_login_http_error_raises(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.post.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=MockResponse({}, 500)
        )

        client = WodAppClient()
        with pytest.raises(WodAppError):
            client.login("user", "pass")


class TestWodAppClientFromSession:
    def test_from_session_creates_authenticated_client(self):
        session = AuthSession(
            token="test_token",
            user_id=1,
            username="test",
            firstname="Test",
            gym_id=100,
            gym_name="Test Gym",
        )
        cache = ApiCacheService()
        client = WodAppClient.from_session(session, cache)

        assert client.is_authenticated is True
        assert client.session.token == "test_token"
        assert client._cache is cache


class TestWodAppClientProperties:
    def test_session_not_authenticated_raises(self):
        client = WodAppClient()
        with pytest.raises(AuthenticationError, match="Not logged in"):
            _ = client.session

    def test_is_authenticated_false_when_not_logged_in(self):
        client = WodAppClient()
        assert client.is_authenticated is False


class TestWodAppClientGetDaySchedule:
    @patch("wodplanner.api.client.httpx.Client")
    def test_get_day_schedule_returns_appointments(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.post.return_value = MockResponse({
            "status": "OK",
            "resultset": [
                {
                    "id_appointment": 1,
                    "id_appointment_type": 10,
                    "id_parent": None,
                    "name": "CrossFit",
                    "date_start": "2026-04-23T10:00:00",
                    "date_end": "2026-04-23T11:00:00",
                    "max_subscriptions": 20,
                    "total_subscriptions": 10,
                    "status": "open",
                    "location": "Box 1",
                    "description": "",
                    "employee_name": "Coach",
                }
            ]
        })

        client = WodAppClient()
        session = AuthSession(
            token="test_token",
            user_id=1,
            username="test",
            firstname="Test",
            gym_id=100,
            gym_name="Test Gym",
            agenda_id=5,
        )
        client._session = session

        appointments = client.get_day_schedule(date(2026, 4, 23))

        assert len(appointments) == 1
        assert appointments[0].name == "CrossFit"
        assert appointments[0].max_subscriptions == 20


class TestWodAppClientGetAppointmentDetails:
    @patch("wodplanner.api.client.httpx.Client")
    def test_get_appointment_details(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.post.return_value = MockResponse({
            "status": "OK",
            "resultset": {
                "id_appointment": 1,
                "id_appointment_type": 10,
                "name": "CrossFit",
                "date_start": "2026-04-23T10:00:00",
                "date_end": "2026-04-23T11:00:00",
                "max_subscriptions": 20,
                "waiting_list": 0,
                "number_hours_before_subscription_opens": 168,
                "subscription_open_date": "",
                "subscribe_not_opened_yet": 0,
                "subscribe_closed": 0,
                "unsubscribe_closed": 0,
                "subscriptions": {
                    "subscribed": 0,
                    "total": 10,
                    "full": 0,
                    "members": [
                        {"name": "Alice", "id_appuser": 1, "imageURL": ""}
                    ]
                },
                "waitinglist": {
                    "total": 0,
                    "members": []
                },
            }
        })

        client = WodAppClient()
        session = AuthSession(
            token="test_token",
            user_id=1,
            username="test",
            firstname="Test",
            gym_id=100,
            gym_name="Test Gym",
            agenda_id=5,
        )
        client._session = session

        details = client.get_appointment_details(
            1,
            datetime(2026, 4, 23, 10, 0),
            datetime(2026, 4, 23, 11, 0),
        )

        assert details.id_appointment == 1
        assert details.subscriptions.total == 10
        assert len(details.subscriptions.members) == 1
        assert details.subscriptions.members[0].name == "Alice"


class TestWodAppClientSubscribeUnsubscribe:
    @patch("wodplanner.api.client.httpx.Client")
    def test_subscribe_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.post.return_value = MockResponse({
            "status": "OK",
            "notice": "",
            "subscribedWithSuccess": 1,
        })

        client = WodAppClient()
        session = AuthSession(
            token="test_token",
            user_id=1,
            username="test",
            firstname="Test",
            gym_id=100,
            gym_name="Test Gym",
            agenda_id=5,
        )
        client._session = session

        result = client.subscribe(
            1,
            datetime(2026, 4, 23, 10, 0),
            datetime(2026, 4, 23, 11, 0),
        )

        assert result.subscribedWithSuccess == 1

    @patch("wodplanner.api.client.httpx.Client")
    def test_unsubscribe_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.post.return_value = MockResponse({
            "status": "OK",
            "notice": "",
            "subscribedWithSuccess": 1,
        })

        client = WodAppClient()
        session = AuthSession(
            token="test_token",
            user_id=1,
            username="test",
            firstname="Test",
            gym_id=100,
            gym_name="Test Gym",
            agenda_id=5,
        )
        client._session = session

        result = client.unsubscribe(
            1,
            datetime(2026, 4, 23, 10, 0),
            datetime(2026, 4, 23, 11, 0),
        )

        assert result.subscribedWithSuccess == 1


class TestWodAppClientFindFriendsInAppointments:
    @patch("wodplanner.api.client.httpx.Client")
    def test_find_friends_in_appointments(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_client.post.side_effect = [
            MockResponse({
                "status": "OK",
                "resultset": [
                    {
                        "id_appointment": 1,
                        "id_appointment_type": 10,
                        "id_parent": None,
                        "name": "CrossFit",
                        "date_start": "2026-04-23T10:00:00",
                        "date_end": "2026-04-23T11:00:00",
                        "max_subscriptions": 20,
                        "total_subscriptions": 1,
                        "status": "open",
                        "location": "",
                        "description": "",
                        "employee_name": "",
                    }
                ]
            }),
            MockResponse({
                "status": "OK",
                "resultset": {
                    "id_appointment": 1,
                    "id_appointment_type": 10,
                    "name": "CrossFit",
                    "date_start": "2026-04-23T10:00:00",
                    "date_end": "2026-04-23T11:00:00",
                    "max_subscriptions": 20,
                    "waiting_list": 0,
                    "number_hours_before_subscription_opens": 168,
                    "subscription_open_date": "",
                    "subscribe_not_opened_yet": 0,
                    "subscribe_closed": 0,
                    "unsubscribe_closed": 0,
                    "subscriptions": {
                        "subscribed": 0,
                        "total": 1,
                        "full": 0,
                        "members": [
                            {"name": "Friend", "id_appuser": 100, "imageURL": ""}
                        ]
                    },
                    "waitinglist": {"total": 0, "members": []},
                }
            }),
        ]

        client = WodAppClient()
        session = AuthSession(
            token="test_token",
            user_id=1,
            username="test",
            firstname="Test",
            gym_id=100,
            gym_name="Test Gym",
            agenda_id=5,
        )
        client._session = session

        result = client.find_friends_in_appointments(
            friend_ids={100},
            day=date(2026, 4, 23),
        )

        assert 1 in result
        assert result[1][0].id_appuser == 100


class TestWodAppClientRetryLogic:
    @patch("wodplanner.api.client.httpx.Client")
    @patch("wodplanner.api.client.time.sleep")
    def test_retries_on_502(self, mock_sleep, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.post.side_effect = [
            MockResponse({}, status_code=502),
            MockResponse({
                "status": "OK",
                "id_user": 1,
                "username": "test",
                "firstname": "Test",
                "token": "token",
                "gyms": [{"id_gym": 1, "idc": 1, "name": "Gym", "city": "City"}],
            }),
            MockResponse({
                "status": "OK",
                "resultset": [{"id_agenda": 1}],
            }),
        ]

        client = WodAppClient()
        session = client.login("user", "pass")

        assert session is not None
        assert mock_client.post.call_count == 3

    @patch("wodplanner.api.client.httpx.Client")
    def test_raises_after_max_retries_502(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.post.return_value = MockResponse({}, status_code=502)

        client = WodAppClient()
        with pytest.raises(WodAppError, match="temporarily unavailable"):
            client.login("user", "pass")


class TestWodAppErrorAndAuthenticationError:
    def test_wodapp_error_is_exception(self):
        err = WodAppError("test error")
        assert str(err) == "test error"

    def test_authentication_error_is_wodapp_error(self):
        err = AuthenticationError("auth error")
        assert isinstance(err, WodAppError)
        assert str(err) == "auth error"


class TestWodAppClientGetUpcomingReservations:
    @patch("wodplanner.api.client.httpx.Client")
    def test_get_upcoming_reservations(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.post.return_value = MockResponse({
            "status": "OK",
            "widgets": {
                "reservations": {
                    "data": [
                        {
                            "id_appointment": 1,
                            "name": "CrossFit",
                            "date_start": "23-04-2026 10:00",
                        },
                        {
                            "id_appointment": 2,
                            "name": "Open Gym",
                            "date_start": "24-04-2026 11:00",
                        },
                    ]
                }
            },
            "companyImages": {"logo": "https://example.com/logo.png"},
        })

        client = WodAppClient()
        session = AuthSession(
            token="test_token",
            user_id=1,
            username="test",
            firstname="Test",
            gym_id=100,
            gym_name="Test Gym",
            agenda_id=5,
        )
        client._session = session

        result, images = client.get_upcoming_reservations()

        assert len(result) == 2
        assert result[0].id_appointment == 1
        assert result[0].name == "CrossFit"
        assert result[1].id_appointment == 2
        assert images == {"logo": "https://example.com/logo.png"}

    @patch("wodplanner.api.client.httpx.Client")
    def test_get_upcoming_reservations_empty(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.post.return_value = MockResponse({
            "status": "OK",
            "widgets": {
                "reservations": {
                    "data": []
                }
            },
            "companyImages": {},
        })

        client = WodAppClient()
        session = AuthSession(
            token="test_token",
            user_id=1,
            username="test",
            firstname="Test",
            gym_id=100,
            gym_name="Test Gym",
            agenda_id=5,
        )
        client._session = session

        result, images = client.get_upcoming_reservations()

        assert result == []
        assert images == {}


class TestWodAppClientGetAppointmentMembers:
    @patch("wodplanner.api.client.httpx.Client")
    def test_get_appointment_members_returns_details(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.post.return_value = MockResponse({
            "status": "OK",
            "resultset": {
                "id_appointment": 1,
                "id_appointment_type": 10,
                "name": "CrossFit",
                "date_start": "2026-04-23T10:00:00",
                "date_end": "2026-04-23T11:00:00",
                "max_subscriptions": 20,
                "waiting_list": 0,
                "subscriptions": {
                    "subscribed": 0,
                    "total": 2,
                    "full": 0,
                    "members": [
                        {"name": "Alice", "id_appuser": 1, "imageURL": ""},
                        {"name": "Bob", "id_appuser": 2, "imageURL": ""},
                    ]
                },
                "waitinglist": {"total": 0, "members": []},
            }
        })

        client = WodAppClient()
        session = AuthSession(
            token="test_token",
            user_id=1,
            username="test",
            firstname="Test",
            gym_id=100,
            gym_name="Test Gym",
            agenda_id=5,
        )
        client._session = session

        members, waitinglist = client.get_appointment_members(
            1,
            datetime(2026, 4, 23, 10, 0),
            datetime(2026, 4, 23, 11, 0),
        )

        assert len(members) == 2
        assert members[0].name == "Alice"
        assert members[1].name == "Bob"
        assert waitinglist.total == 0

    @patch("wodplanner.api.client.httpx.Client")
    def test_get_appointment_members_uses_cache(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.post.return_value = MockResponse({
            "status": "OK",
            "resultset": {
                "id_appointment": 1,
                "id_appointment_type": 10,
                "name": "CrossFit",
                "date_start": "2026-04-23T10:00:00",
                "date_end": "2026-04-23T11:00:00",
                "max_subscriptions": 20,
                "waiting_list": 0,
                "subscriptions": {
                    "subscribed": 0,
                    "total": 2,
                    "full": 0,
                    "members": [
                        {"name": "Alice", "id_appuser": 1, "imageURL": ""},
                    ]
                },
                "waitinglist": {"total": 0, "members": []},
            }
        })

        cache = ApiCacheService(ttl_seconds=120)
        client = WodAppClient()
        client._cache = cache
        session = AuthSession(
            token="test_token",
            user_id=1,
            username="test",
            firstname="Test",
            gym_id=100,
            gym_name="Test Gym",
            agenda_id=5,
        )
        client._session = session

        cache_key = f"5:1:{datetime(2026, 4, 23, 10, 0).isoformat()}:{datetime(2026, 4, 23, 11, 0).isoformat()}"
        pre_cache_members = [Member(id_appuser=99, name="CachedUser", imageURL="")]
        cache.set(cache_key, (pre_cache_members, WaitingList(total=0, members=[])))

        members, waitinglist = client.get_appointment_members(
            1,
            datetime(2026, 4, 23, 10, 0),
            datetime(2026, 4, 23, 11, 0),
        )

        assert len(members) == 1
        assert members[0].id_appuser == 99
        assert mock_client.post.call_count == 0

    @patch("wodplanner.api.client.httpx.Client")
    def test_get_appointment_members_cache_stale_on_count_mismatch(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.post.return_value = MockResponse({
            "status": "OK",
            "resultset": {
                "id_appointment": 1,
                "id_appointment_type": 10,
                "name": "CrossFit",
                "date_start": "2026-04-23T10:00:00",
                "date_end": "2026-04-23T11:00:00",
                "max_subscriptions": 20,
                "waiting_list": 0,
                "subscriptions": {
                    "subscribed": 0,
                    "total": 2,
                    "full": 0,
                    "members": [
                        {"name": "Alice", "id_appuser": 1, "imageURL": ""},
                    ]
                },
                "waitinglist": {"total": 0, "members": []},
            }
        })

        cache = ApiCacheService(ttl_seconds=120)
        client = WodAppClient()
        client._cache = cache
        session = AuthSession(
            token="test_token",
            user_id=1,
            username="test",
            firstname="Test",
            gym_id=100,
            gym_name="Test Gym",
            agenda_id=5,
        )
        client._session = session

        cache_key = f"5:1:{datetime(2026, 4, 23, 10, 0).isoformat()}:{datetime(2026, 4, 23, 11, 0).isoformat()}"
        pre_cache_members = [Member(id_appuser=99, name="CachedUser", imageURL="")]
        cache.set(cache_key, (pre_cache_members, WaitingList(total=0, members=[])))

        members, waitinglist = client.get_appointment_members(
            1,
            datetime(2026, 4, 23, 10, 0),
            datetime(2026, 4, 23, 11, 0),
            expected_total=2,
        )

        assert len(members) == 1
        assert members[0].name == "Alice"
        assert mock_client.post.call_count == 1