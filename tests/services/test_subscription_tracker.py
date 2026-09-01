"""Tests for SubscriptionTrackerService."""

from datetime import date, datetime, timedelta

from wodplanner.models.calendar import Reservation
from wodplanner.services.subscription_tracker import SubscriptionTrackerService


class TestRecordSubscribe:
    def test_records_subscribe(self, db_path, make_user):
        make_user(1)
        svc = SubscriptionTrackerService(db_path)
        svc.record_subscribe(user_id=1, appointment_id=10, class_name="CrossFit", class_date=date(2026, 6, 1))
        assert svc.has_any_events(1)
        assert not svc.has_any_events(2)

    def test_records_any_class_type(self, db_path, make_user):
        make_user(1)
        svc = SubscriptionTrackerService(db_path)
        svc.record_subscribe(user_id=1, appointment_id=10, class_name="Yoga", class_date=date(2026, 6, 1))
        assert svc.has_any_events(1)


class TestRecordUnsubscribe:
    def test_records_unsubscribe(self, db_path, make_user):
        make_user(1)
        svc = SubscriptionTrackerService(db_path)
        svc.record_subscribe(user_id=1, appointment_id=10, class_name="CrossFit", class_date=date(2026, 6, 1))
        svc.record_unsubscribe(user_id=1, appointment_id=10, class_name="CrossFit", class_date=date(2026, 6, 1))
        assert svc.has_any_events(1)

    def test_ignores_unsubscribe_without_prior_subscribe(self, db_path, make_user):
        make_user(1)
        svc = SubscriptionTrackerService(db_path)
        svc.record_unsubscribe(user_id=1, appointment_id=10, class_name="CrossFit", class_date=date(2026, 6, 1))
        assert not svc.has_any_events(1)

    def test_sub_then_unsub_net_zero_for_week(self, db_path, make_user):
        make_user(1)
        svc = SubscriptionTrackerService(db_path)
        svc.record_subscribe(user_id=1, appointment_id=10, class_name="CrossFit", class_date=date(2026, 6, 1))
        svc.record_unsubscribe(user_id=1, appointment_id=10, class_name="CrossFit", class_date=date(2026, 6, 1))
        weekly = svc.get_weekly_counts(user_id=1, weeks=52)
        target_monday = date(2026, 6, 1) - timedelta(days=date(2026, 6, 1).weekday())
        for w in weekly:
            if w["week_start"] == target_monday.isoformat():
                assert w["past"] == 0
                break


class TestWeeklyCounts:
    def test_single_past_session(self, db_path, make_user):
        make_user(1)
        svc = SubscriptionTrackerService(db_path)
        svc.record_subscribe(user_id=1, appointment_id=10, class_name="CrossFit", class_date=date(2026, 5, 1))
        weekly = svc.get_weekly_counts(user_id=1, weeks=52)
        target_monday = date(2026, 5, 1) - timedelta(days=date(2026, 5, 1).weekday())
        for w in weekly:
            if w["week_start"] == target_monday.isoformat():
                assert w["past"] == 1
                assert w["future"] == 0
                break

    def test_multiple_sessions_same_week(self, db_path, make_user):
        make_user(1)
        svc = SubscriptionTrackerService(db_path)
        svc.record_subscribe(user_id=1, appointment_id=10, class_name="CrossFit", class_date=date(2026, 5, 4))
        svc.record_subscribe(user_id=1, appointment_id=11, class_name="CrossFit", class_date=date(2026, 5, 6))
        weekly = svc.get_weekly_counts(user_id=1, weeks=52)
        target_monday = date(2026, 5, 4) - timedelta(days=date(2026, 5, 4).weekday())
        for w in weekly:
            if w["week_start"] == target_monday.isoformat():
                assert w["past"] == 2
                break

    def test_returns_52_weeks(self, db_path, make_user):
        make_user(1)
        svc = SubscriptionTrackerService(db_path)
        svc.record_subscribe(user_id=1, appointment_id=1, class_name="CrossFit", class_date=date(2026, 1, 1))
        weekly = svc.get_weekly_counts(user_id=1, weeks=52)
        assert len(weekly) == 52

    def test_user_scoping(self, db_path, make_user):
        make_user(1, 2)
        svc = SubscriptionTrackerService(db_path)
        svc.record_subscribe(user_id=1, appointment_id=10, class_name="CrossFit", class_date=date(2026, 5, 1))
        svc.record_subscribe(user_id=2, appointment_id=11, class_name="CrossFit", class_date=date(2026, 5, 2))
        weekly_user1 = svc.get_weekly_counts(user_id=1, weeks=52)
        weekly_user2 = svc.get_weekly_counts(user_id=2, weeks=52)
        target_monday = date(2026, 5, 1) - timedelta(days=date(2026, 5, 1).weekday())
        target_key = target_monday.isoformat()
        for w in weekly_user1:
            if w["week_start"] == target_key:
                assert w["past"] == 1
                break
        for w in weekly_user2:
            if w["week_start"] == target_key:
                assert w["past"] == 1
                break

    def test_pre_existing_unsubscribe_ignored(self, db_path, make_user):
        make_user(1)
        svc = SubscriptionTrackerService(db_path)
        svc.record_unsubscribe(user_id=1, appointment_id=10, class_name="CrossFit", class_date=date(2026, 7, 12))
        svc.record_subscribe(user_id=1, appointment_id=10, class_name="CrossFit", class_date=date(2026, 7, 12))
        weekly = svc.get_weekly_counts(user_id=1, weeks=52)
        target_monday = date(2026, 7, 12) - timedelta(days=date(2026, 7, 12).weekday())
        target_key = target_monday.isoformat()
        for w in weekly:
            if w["week_start"] == target_key:
                assert w["future"] == 1 or w["past"] == 1
                break


class TestCurrentWeekStats:
    def test_returns_counts(self, db_path, make_user):
        make_user(1)
        svc = SubscriptionTrackerService(db_path)
        today = date.today()
        svc.record_subscribe(user_id=1, appointment_id=10, class_name="CrossFit", class_date=today)
        stats = svc.get_current_week_stats(user_id=1)
        assert stats["future"] >= 1


class TestAveragePerWeek:
    def test_no_data_returns_zero(self, db_path):
        svc = SubscriptionTrackerService(db_path)
        assert svc.get_average_per_week(1) == 0.0

    def test_one_week_one_session(self, db_path, make_user):
        make_user(1)
        svc = SubscriptionTrackerService(db_path)
        past_date = date.today() - timedelta(days=10)
        svc.record_subscribe(user_id=1, appointment_id=10, class_name="CrossFit", class_date=past_date)
        avg = svc.get_average_per_week(1)
        assert avg > 0


class TestWeeksTracked:
    def test_returns_zero_when_no_data(self, db_path):
        svc = SubscriptionTrackerService(db_path)
        assert svc.get_weeks_tracked(1) == 0

    def test_counts_distinct_weeks(self, db_path, make_user):
        make_user(1)
        svc = SubscriptionTrackerService(db_path)
        past = date.today() - timedelta(days=30)
        svc.record_subscribe(user_id=1, appointment_id=10, class_name="CrossFit", class_date=past)
        weeks = svc.get_weeks_tracked(1)
        assert weeks > 0


class TestDeleteAllForUser:
    def test_deletes_all_events_for_user(self, db_path, make_user):
        make_user(1, 2)
        svc = SubscriptionTrackerService(db_path)
        svc.record_subscribe(user_id=1, appointment_id=10, class_name="CrossFit", class_date=date(2026, 6, 1))
        svc.record_subscribe(user_id=1, appointment_id=11, class_name="CrossFit", class_date=date(2026, 6, 2))
        svc.record_subscribe(user_id=2, appointment_id=12, class_name="CrossFit", class_date=date(2026, 6, 1))
        svc.delete_all_for_user(user_id=1)
        assert not svc.has_any_events(1)
        assert svc.has_any_events(2)

    def test_noop_when_no_data(self, db_path, make_user):
        make_user(1)
        svc = SubscriptionTrackerService(db_path)
        svc.delete_all_for_user(user_id=1)
        assert not svc.has_any_events(1)


class TestWaitlist:
    def test_records_waitlist(self, db_path, make_user):
        make_user(1)
        svc = SubscriptionTrackerService(db_path)
        svc.record_waitlist(user_id=1, appointment_id=10, class_name="CrossFit", class_date=date(2026, 7, 1))
        assert svc.has_any_events(1)

    def test_waitlist_idempotent(self, db_path, make_user):
        make_user(1)
        svc = SubscriptionTrackerService(db_path)
        svc.record_waitlist(user_id=1, appointment_id=10, class_name="CrossFit", class_date=date(2026, 7, 1))
        svc.record_waitlist(user_id=1, appointment_id=10, class_name="CrossFit", class_date=date(2026, 7, 1))
        assert svc.has_any_events(1)

    def test_waitlist_not_counted_in_graph(self, db_path, make_user):
        make_user(1)
        svc = SubscriptionTrackerService(db_path)
        svc.record_waitlist(user_id=1, appointment_id=10, class_name="CrossFit", class_date=date(2026, 5, 1))
        weekly = svc.get_weekly_counts(user_id=1, weeks=52)
        target_monday = date(2026, 5, 1) - timedelta(days=date(2026, 5, 1).weekday())
        for w in weekly:
            if w["week_start"] == target_monday.isoformat():
                assert w["past"] == 0
                assert w["future"] == 0
                break

    def test_promote_waitlist(self, db_path, make_user):
        make_user(1)
        svc = SubscriptionTrackerService(db_path)
        svc.record_waitlist(user_id=1, appointment_id=10, class_name="CrossFit", class_date=date(2026, 7, 1))
        promoted = svc.promote_waitlist(user_id=1, appointment_id=10, class_date=date(2026, 7, 1))
        assert promoted

    def test_promote_noop_on_missing(self, db_path, make_user):
        make_user(1)
        svc = SubscriptionTrackerService(db_path)
        promoted = svc.promote_waitlist(user_id=1, appointment_id=99, class_date=date(2026, 7, 1))
        assert not promoted

    def test_promoted_waitlist_counts_in_graph(self, db_path, make_user):
        make_user(1)
        svc = SubscriptionTrackerService(db_path)
        svc.record_waitlist(user_id=1, appointment_id=10, class_name="CrossFit", class_date=date(2026, 5, 1))
        svc.promote_waitlist(user_id=1, appointment_id=10, class_date=date(2026, 5, 1))
        weekly = svc.get_weekly_counts(user_id=1, weeks=52)
        target_monday = date(2026, 5, 1) - timedelta(days=date(2026, 5, 1).weekday())
        for w in weekly:
            if w["week_start"] == target_monday.isoformat():
                assert w["past"] == 1
                break

    def test_reconcile_from_reservations(self, db_path, make_user):
        make_user(1)
        svc = SubscriptionTrackerService(db_path)
        svc.record_waitlist(user_id=1, appointment_id=10, class_name="CrossFit", class_date=date(2026, 7, 1))
        svc.record_waitlist(user_id=1, appointment_id=11, class_name="CrossFit", class_date=date(2026, 7, 3))
        reservations = [
            Reservation(id_appointment=10, name="CrossFit", date_start=datetime(2026, 7, 1, 10, 0)),
            Reservation(id_appointment=11, name="CrossFit", date_start=datetime(2026, 7, 3, 10, 0)),
        ]
        count = svc.reconcile_from_reservations(1, reservations)
        assert count == 2
        weekly = svc.get_weekly_counts(user_id=1, weeks=52)
        target_monday = date(2026, 7, 1) - timedelta(days=date(2026, 7, 1).weekday())
        for w in weekly:
            if w["week_start"] == target_monday.isoformat():
                assert w["past"] == 2
                break

    def test_reconcile_ignores_non_waitlist(self, db_path, make_user):
        make_user(1)
        svc = SubscriptionTrackerService(db_path)
        reservations = [
            Reservation(id_appointment=10, name="CrossFit", date_start=datetime(2026, 7, 1, 10, 0)),
        ]
        count = svc.reconcile_from_reservations(1, reservations)
        assert count == 0