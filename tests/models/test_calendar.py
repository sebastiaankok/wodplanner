"""Tests for models/calendar.py"""

from datetime import datetime

from wodplanner.models.calendar import (
    Appointment,
    AppointmentDetails,
    DaySchedule,
    Member,
    SubscribeResponse,
    Subscriptions,
    WaitingList,
)


class TestAppointment:
    def test_required_fields(self):
        appt = Appointment(
            id_appointment=1,
            id_appointment_type=2,
            name="CrossFit",
            date_start=datetime(2026, 1, 1, 9, 0),
            date_end=datetime(2026, 1, 1, 10, 0),
            max_subscriptions=20,
            total_subscriptions=10,
            status="open",
        )
        assert appt.id_appointment == 1
        assert appt.name == "CrossFit"
        assert appt.max_subscriptions == 20

    def test_optional_fields_default(self):
        appt = Appointment(
            id_appointment=1,
            id_appointment_type=2,
            name="CrossFit",
            date_start=datetime(2026, 1, 1, 9, 0),
            date_end=datetime(2026, 1, 1, 10, 0),
            max_subscriptions=20,
            total_subscriptions=10,
            status="open",
        )
        assert appt.location == ""
        assert appt.description == ""
        assert appt.employee_name == ""
        assert appt.id_parent is None


class TestDaySchedule:
    def test_required_fields(self):
        ds = DaySchedule(status="ok", resultset=[])
        assert ds.status == "ok"
        assert ds.resultset == []

    def test_optional_notice_default(self):
        ds = DaySchedule(status="ok", resultset=[])
        assert ds.notice == ""


class TestMember:
    def test_required_fields(self):
        member = Member(name="John Doe", id_appuser=1)
        assert member.name == "John Doe"
        assert member.id_appuser == 1

    def test_optional_id_partner_default(self):
        member = Member(name="John Doe", id_appuser=1)
        assert member.id_partner == 0

    def test_image_url_alias(self):
        member = Member(name="John Doe", id_appuser=1, imageURL="http://example.com/img.jpg")
        assert member.imageURL == "http://example.com/img.jpg"


class TestSubscriptions:
    def test_required_fields(self):
        subs = Subscriptions(subscribed=1, total=10, full=0, members=[])
        assert subs.subscribed == 1
        assert subs.total == 10
        assert subs.full == 0


class TestWaitingList:
    def test_required_fields(self):
        wl = WaitingList(total=5, members=[])
        assert wl.total == 5


class TestAppointmentDetails:
    def test_is_open_for_signup(self):
        appt = AppointmentDetails(
            id_appointment=1,
            id_appointment_type=2,
            name="CrossFit",
            date_start=datetime(2026, 1, 1, 9, 0),
            date_end=datetime(2026, 1, 1, 10, 0),
            max_subscriptions=20,
            waiting_list=0,
            number_hours_before_subscription_opens=24,
            subscription_open_date="01-01-2026 09:00",
            subscribe_not_opened_yet=0,
            subscribe_closed=0,
            unsubscribe_closed=0,
            subscriptions=Subscriptions(subscribed=0, total=5, full=0, members=[]),
            waitinglist=WaitingList(total=0, members=[]),
        )
        assert appt.is_open_for_signup() is True

    def test_is_open_for_signup_not_yet_open(self):
        appt = AppointmentDetails(
            id_appointment=1,
            id_appointment_type=2,
            name="CrossFit",
            date_start=datetime(2026, 1, 1, 9, 0),
            date_end=datetime(2026, 1, 1, 10, 0),
            max_subscriptions=20,
            waiting_list=0,
            number_hours_before_subscription_opens=24,
            subscription_open_date="01-01-2026 09:00",
            subscribe_not_opened_yet=1,
            subscribe_closed=0,
            unsubscribe_closed=0,
            subscriptions=Subscriptions(subscribed=0, total=5, full=0, members=[]),
            waitinglist=WaitingList(total=0, members=[]),
        )
        assert appt.is_open_for_signup() is False

    def test_is_open_for_signup_closed(self):
        appt = AppointmentDetails(
            id_appointment=1,
            id_appointment_type=2,
            name="CrossFit",
            date_start=datetime(2026, 1, 1, 9, 0),
            date_end=datetime(2026, 1, 1, 10, 0),
            max_subscriptions=20,
            waiting_list=0,
            number_hours_before_subscription_opens=24,
            subscription_open_date="01-01-2026 09:00",
            subscribe_not_opened_yet=0,
            subscribe_closed=1,
            unsubscribe_closed=0,
            subscriptions=Subscriptions(subscribed=0, total=5, full=0, members=[]),
            waitinglist=WaitingList(total=0, members=[]),
        )
        assert appt.is_open_for_signup() is False

    def test_has_spots_available(self):
        appt = AppointmentDetails(
            id_appointment=1,
            id_appointment_type=2,
            name="CrossFit",
            date_start=datetime(2026, 1, 1, 9, 0),
            date_end=datetime(2026, 1, 1, 10, 0),
            max_subscriptions=20,
            waiting_list=0,
            number_hours_before_subscription_opens=24,
            subscription_open_date="01-01-2026 09:00",
            subscribe_not_opened_yet=0,
            subscribe_closed=0,
            unsubscribe_closed=0,
            subscriptions=Subscriptions(subscribed=0, total=10, full=0, members=[]),
            waitinglist=WaitingList(total=0, members=[]),
        )
        assert appt.has_spots_available() is True

    def test_no_spots_available(self):
        appt = AppointmentDetails(
            id_appointment=1,
            id_appointment_type=2,
            name="CrossFit",
            date_start=datetime(2026, 1, 1, 9, 0),
            date_end=datetime(2026, 1, 1, 10, 0),
            max_subscriptions=20,
            waiting_list=0,
            number_hours_before_subscription_opens=24,
            subscription_open_date="01-01-2026 09:00",
            subscribe_not_opened_yet=0,
            subscribe_closed=0,
            unsubscribe_closed=0,
            subscriptions=Subscriptions(subscribed=0, total=20, full=1, members=[]),
            waitinglist=WaitingList(total=0, members=[]),
        )
        assert appt.has_spots_available() is False

    def test_is_user_subscribed(self):
        appt = AppointmentDetails(
            id_appointment=1,
            id_appointment_type=2,
            name="CrossFit",
            date_start=datetime(2026, 1, 1, 9, 0),
            date_end=datetime(2026, 1, 1, 10, 0),
            max_subscriptions=20,
            waiting_list=0,
            number_hours_before_subscription_opens=24,
            subscription_open_date="01-01-2026 09:00",
            subscribe_not_opened_yet=0,
            subscribe_closed=0,
            unsubscribe_closed=0,
            subscriptions=Subscriptions(subscribed=1, total=10, full=0, members=[]),
            waitinglist=WaitingList(total=0, members=[]),
        )
        assert appt.is_user_subscribed() is True

    def test_is_user_not_subscribed(self):
        appt = AppointmentDetails(
            id_appointment=1,
            id_appointment_type=2,
            name="CrossFit",
            date_start=datetime(2026, 1, 1, 9, 0),
            date_end=datetime(2026, 1, 1, 10, 0),
            max_subscriptions=20,
            waiting_list=0,
            number_hours_before_subscription_opens=24,
            subscription_open_date="01-01-2026 09:00",
            subscribe_not_opened_yet=0,
            subscribe_closed=0,
            unsubscribe_closed=0,
            subscriptions=Subscriptions(subscribed=0, total=10, full=0, members=[]),
            waitinglist=WaitingList(total=0, members=[]),
        )
        assert appt.is_user_subscribed() is False

    def test_get_member_ids(self):
        member1 = Member(name="John", id_appuser=1)
        member2 = Member(name="Jane", id_appuser=2)
        appt = AppointmentDetails(
            id_appointment=1,
            id_appointment_type=2,
            name="CrossFit",
            date_start=datetime(2026, 1, 1, 9, 0),
            date_end=datetime(2026, 1, 1, 10, 0),
            max_subscriptions=20,
            waiting_list=0,
            number_hours_before_subscription_opens=24,
            subscription_open_date="01-01-2026 09:00",
            subscribe_not_opened_yet=0,
            subscribe_closed=0,
            unsubscribe_closed=0,
            subscriptions=Subscriptions(subscribed=0, total=2, full=0, members=[member1, member2]),
            waitinglist=WaitingList(total=0, members=[]),
        )
        assert appt.get_member_ids() == {1, 2}


class TestSubscribeResponse:
    def test_required_fields(self):
        resp = SubscribeResponse(status="ok")
        assert resp.status == "ok"

    def test_optional_notice_default(self):
        resp = SubscribeResponse(status="ok")
        assert resp.notice == ""

    def test_optional_subscribed_default(self):
        resp = SubscribeResponse(status="ok")
        assert resp.subscribedWithSuccess == 0
