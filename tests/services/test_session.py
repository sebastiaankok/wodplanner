
from wodplanner.models.auth import AuthSession
from wodplanner.services import session


class TestEncode:
    def test_encode_returns_string(self):
        auth_session = AuthSession(
            token="test_token",
            user_id=1,
            username="testuser",
            firstname="Test",
            gym_id=100,
            gym_name="Test Gym",
        )
        result = session.encode(auth_session, "secret_key")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_encode_different_sessions_produce_different_cookies(self):
        auth1 = AuthSession(
            token="token1",
            user_id=1,
            username="user1",
            firstname="User",
            gym_id=100,
            gym_name="Gym",
        )
        auth2 = AuthSession(
            token="token2",
            user_id=2,
            username="user2",
            firstname="User",
            gym_id=200,
            gym_name="Gym",
        )
        result1 = session.encode(auth1, "secret_key")
        result2 = session.encode(auth2, "secret_key")
        assert result1 != result2

    def test_encode_different_keys_produce_different_cookies(self):
        auth = AuthSession(
            token="token",
            user_id=1,
            username="user",
            firstname="User",
            gym_id=100,
            gym_name="Gym",
        )
        result1 = session.encode(auth, "secret_key_1")
        result2 = session.encode(auth, "secret_key_2")
        assert result1 != result2


class TestDecode:
    def test_decode_valid_cookie_returns_session(self):
        auth_session = AuthSession(
            token="test_token",
            user_id=1,
            username="testuser",
            firstname="Test",
            gym_id=100,
            gym_name="Test Gym",
        )
        cookie = session.encode(auth_session, "secret_key")
        result = session.decode(cookie, "secret_key", max_age_seconds=None)
        assert result is not None
        assert result.token == "test_token"
        assert result.user_id == 1
        assert result.username == "testuser"

    def test_decode_wrong_secret_returns_none(self):
        auth_session = AuthSession(
            token="test_token",
            user_id=1,
            username="testuser",
            firstname="Test",
            gym_id=100,
            gym_name="Test Gym",
        )
        cookie = session.encode(auth_session, "secret_key")
        result = session.decode(cookie, "wrong_key", max_age_seconds=None)
        assert result is None

    def test_decode_tampered_cookie_returns_none(self):
        cookie = "dHlwZT1hdXRoLnRva2VuIWR1bXB5Z29vZ2xl"
        result = session.decode(cookie, "secret_key", max_age_seconds=None)
        assert result is None

    def test_decode_expired_cookie_returns_none(self):
        auth_session = AuthSession(
            token="test_token",
            user_id=1,
            username="testuser",
            firstname="Test",
            gym_id=100,
            gym_name="Test Gym",
        )
        cookie = session.encode(auth_session, "secret_key")
        result = session.decode(cookie, "secret_key", max_age_seconds=-1)
        assert result is None

    def test_decode_with_agenda_id(self):
        auth_session = AuthSession(
            token="test_token",
            user_id=1,
            username="testuser",
            firstname="Test",
            gym_id=100,
            gym_name="Test Gym",
            agenda_id=42,
        )
        cookie = session.encode(auth_session, "secret_key")
        result = session.decode(cookie, "secret_key", max_age_seconds=None)
        assert result is not None
        assert result.agenda_id == 42