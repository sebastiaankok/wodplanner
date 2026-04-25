"""Tests for models/auth.py"""

import pytest
from pydantic import ValidationError

from wodplanner.models.auth import AuthSession, Gym, LoginResponse


class TestGym:
    def test_required_fields(self):
        gym = Gym(id_gym=1, idc=2, name="Test Gym", city="Test City")
        assert gym.id_gym == 1
        assert gym.idc == 2
        assert gym.name == "Test Gym"
        assert gym.city == "Test City"

    def test_unsubscribed_default(self):
        gym = Gym(id_gym=1, idc=2, name="Test Gym", city="Test City")
        assert gym.unsubscribed_for_mailing == 0

    def test_unsubscribed_overridden(self):
        gym = Gym(id_gym=1, idc=2, name="Test Gym", city="Test City", unsubscribed_for_mailing=1)
        assert gym.unsubscribed_for_mailing == 1

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            Gym(id_gym=1, name="Test Gym", city="Test City")  # missing idc


class TestLoginResponse:
    def test_required_fields(self):
        resp = LoginResponse(
            status="ok",
            id_user=1,
            username="testuser",
            firstname="Test",
            token="abc123",
            gyms=[],
        )
        assert resp.status == "ok"
        assert resp.id_user == 1
        assert resp.username == "testuser"
        assert resp.firstname == "Test"
        assert resp.token == "abc123"

    def test_optional_notice_default(self):
        resp = LoginResponse(
            status="ok",
            id_user=1,
            username="testuser",
            firstname="Test",
            token="abc123",
            gyms=[],
        )
        assert resp.notice == ""

    def test_optional_id_appuser_default(self):
        resp = LoginResponse(
            status="ok",
            id_user=1,
            username="testuser",
            firstname="Test",
            token="abc123",
            gyms=[],
        )
        assert resp.id_appuser is None

    def test_gyms_list(self):
        gym = Gym(id_gym=1, idc=2, name="Test Gym", city="Test City")
        resp = LoginResponse(
            status="ok",
            id_user=1,
            username="testuser",
            firstname="Test",
            token="abc123",
            gyms=[gym],
        )
        assert len(resp.gyms) == 1
        assert resp.gyms[0].name == "Test Gym"


class TestAuthSession:
    def test_required_fields(self):
        session = AuthSession(
            token="abc123",
            user_id=1,
            username="testuser",
            firstname="Test",
            gym_id=2,
            gym_name="Test Gym",
        )
        assert session.token == "abc123"
        assert session.user_id == 1
        assert session.gym_id == 2

    def test_optional_appuser_id_default(self):
        session = AuthSession(
            token="abc123",
            user_id=1,
            username="testuser",
            firstname="Test",
            gym_id=2,
            gym_name="Test Gym",
        )
        assert session.appuser_id is None

    def test_optional_agenda_id_default(self):
        session = AuthSession(
            token="abc123",
            user_id=1,
            username="testuser",
            firstname="Test",
            gym_id=2,
            gym_name="Test Gym",
        )
        assert session.agenda_id is None

    def test_all_fields(self):
        session = AuthSession(
            token="abc123",
            user_id=1,
            appuser_id=10,
            username="testuser",
            firstname="Test",
            gym_id=2,
            gym_name="Test Gym",
            agenda_id=5,
        )
        assert session.appuser_id == 10
        assert session.agenda_id == 5
