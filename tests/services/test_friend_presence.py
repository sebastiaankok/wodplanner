"""Tests for services/friend_presence.py"""

from datetime import datetime
from unittest.mock import MagicMock

from wodplanner.models.calendar import Appointment, Member
from wodplanner.models.friends import Friend
from wodplanner.services.friend_presence import find_friends_in_appointments


def make_appt(appt_id: int, total: int = 0) -> Appointment:
    return Appointment(
        id_appointment=appt_id,
        id_appointment_type=1,
        name="CrossFit",
        date_start=datetime(2026, 5, 1, 9, 0),
        date_end=datetime(2026, 5, 1, 10, 0),
        max_subscriptions=20,
        total_subscriptions=total,
        status="open",
    )


def make_friend(appuser_id: int, name: str = "Alice") -> Friend:
    return Friend(owner_user_id=1, appuser_id=appuser_id, name=name)


def make_member(appuser_id: int, name: str = "Alice") -> Member:
    return Member(name=name, id_appuser=appuser_id)


class TestFindFriendsInAppointments:
    def test_empty_friends_returns_empty_dict_no_api_calls(self):
        client = MagicMock()
        appts = [make_appt(1), make_appt(2)]

        result = find_friends_in_appointments(appts, [], client)

        assert result == {}
        client.get_appointment_members.assert_not_called()

    def test_friend_present_in_appointment_returns_friend_object(self):
        client = MagicMock()
        friend = make_friend(appuser_id=42, name="Bob")
        appt = make_appt(1, total=1)
        client.get_appointment_members.return_value = ([make_member(42, "Bob")], MagicMock())

        result = find_friends_in_appointments([appt], [friend], client)

        assert result[1] == [friend]

    def test_member_not_in_friends_excluded(self):
        client = MagicMock()
        friend = make_friend(appuser_id=42)
        appt = make_appt(1, total=2)
        client.get_appointment_members.return_value = (
            [make_member(42), make_member(99, "Stranger")],
            MagicMock(),
        )

        result = find_friends_in_appointments([appt], [friend], client)

        assert len(result[1]) == 1
        assert result[1][0].appuser_id == 42

    def test_fetch_failure_maps_to_none(self):
        client = MagicMock()
        friend = make_friend(appuser_id=42)
        appt = make_appt(1)
        client.get_appointment_members.side_effect = RuntimeError("network error")

        result = find_friends_in_appointments([appt], [friend], client)

        assert result[1] is None

    def test_fetch_failure_does_not_affect_other_appointments(self):
        client = MagicMock()
        friend = make_friend(appuser_id=42, name="Alice")
        appt_ok = make_appt(1, total=1)
        appt_fail = make_appt(2)

        def side_effect(appt_id, *args, **kwargs):
            if appt_id == 2:
                raise RuntimeError("fail")
            return [make_member(42, "Alice")], MagicMock()

        client.get_appointment_members.side_effect = side_effect

        result = find_friends_in_appointments([appt_ok, appt_fail], [friend], client)

        assert result[1] == [friend]
        assert result[2] is None

    def test_no_friends_in_appointment_returns_empty_list(self):
        client = MagicMock()
        friend = make_friend(appuser_id=42)
        appt = make_appt(1, total=1)
        client.get_appointment_members.return_value = ([make_member(99, "Other")], MagicMock())

        result = find_friends_in_appointments([appt], [friend], client)

        assert result[1] == []

    def test_fetch_failure_logs_warning(self, caplog):
        import logging

        client = MagicMock()
        friend = make_friend(appuser_id=42)
        appt = make_appt(7)
        client.get_appointment_members.side_effect = ValueError("boom")

        with caplog.at_level(logging.WARNING, logger="wodplanner.services.friend_presence"):
            find_friends_in_appointments([appt], [friend], client)

        assert any("7" in r.message for r in caplog.records)

    def test_multiple_friends_in_one_appointment(self):
        client = MagicMock()
        f1 = make_friend(appuser_id=1, name="Alice")
        f2 = make_friend(appuser_id=2, name="Bob")
        appt = make_appt(10, total=2)
        client.get_appointment_members.return_value = (
            [make_member(1, "Alice"), make_member(2, "Bob")],
            MagicMock(),
        )

        result = find_friends_in_appointments([appt], [f1, f2], client)

        assert len(result[10]) == 2
        assert {fr.appuser_id for fr in result[10]} == {1, 2}
