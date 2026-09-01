"""Tests for DataShareService."""
from wodplanner.services.friends import DataShareService
from wodplanner.services.users import UserService


class TestDataShareService:
    def test_send_request_creates_pending(self, db_path, make_user):
        make_user(1, 2)
        svc = DataShareService(db_path)
        assert svc.send_request(1, 2) is True
        assert svc.get_share_status(1, 2) == "pending_outgoing"
        assert svc.get_share_status(2, 1) == "pending_incoming"

    def test_self_request_returns_false(self, db_path, make_user):
        make_user(1)
        svc = DataShareService(db_path)
        assert svc.send_request(1, 1) is False

    def test_duplicate_request_returns_false(self, db_path, make_user):
        make_user(1, 2)
        svc = DataShareService(db_path)
        svc.send_request(1, 2)
        assert svc.send_request(1, 2) is True

    def test_accept_request(self, db_path, make_user):
        make_user(1, 2)
        svc = DataShareService(db_path)
        svc.send_request(1, 2)
        assert svc.accept_request(2, 1) is True
        assert svc.get_share_status(1, 2) == "accepted"
        assert svc.get_share_status(2, 1) == "accepted"

    def test_accept_nonexistent_returns_false(self, db_path, make_user):
        make_user(1, 2)
        svc = DataShareService(db_path)
        assert svc.accept_request(2, 1) is False

    def test_decline_request(self, db_path, make_user):
        make_user(1, 2)
        svc = DataShareService(db_path)
        svc.send_request(1, 2)
        assert svc.decline_request(2, 1) is True
        assert svc.get_share_status(1, 2) is None

    def test_cancel_request_and_resend(self, db_path, make_user):
        make_user(1, 2)
        svc = DataShareService(db_path)
        svc.send_request(1, 2)
        assert svc.get_share_status(1, 2) == "pending_outgoing"
        assert svc.cancel_request(1, 2) is True
        assert svc.get_share_status(1, 2) is None
        assert svc.send_request(1, 2) is True
        assert svc.get_share_status(1, 2) == "pending_outgoing"

    def test_revoke_share(self, db_path, make_user):
        make_user(1, 2)
        svc = DataShareService(db_path)
        svc.send_request(1, 2)
        svc.accept_request(2, 1)
        assert svc.revoke_share(1, 2) is True
        assert svc.get_share_status(1, 2) is None

    def test_get_incoming_requests(self, db_path, make_user):
        make_user(1, 2, 3)
        svc = DataShareService(db_path)
        svc.send_request(2, 1)
        svc.send_request(3, 1)
        incoming = svc.get_incoming_requests(1)
        assert sorted(incoming) == [2, 3]

    def test_get_outgoing_requests(self, db_path, make_user):
        make_user(1, 2, 3)
        svc = DataShareService(db_path)
        svc.send_request(1, 2)
        svc.send_request(1, 3)
        outgoing = svc.get_outgoing_requests(1)
        assert sorted(outgoing) == [2, 3]

    def test_get_partners(self, db_path, make_user):
        make_user(1, 2, 3)
        svc = DataShareService(db_path)
        svc.send_request(1, 2)
        svc.accept_request(2, 1)
        svc.send_request(3, 1)
        svc.accept_request(1, 3)
        partners = svc.get_partners(1)
        assert sorted(partners) == [2, 3]

    def test_get_partner_users(self, db_path, make_user):
        user_svc = make_user(1, 2)
        svc = DataShareService(db_path)
        svc.send_request(1, 2)
        svc.accept_request(2, 1)
        partners = svc.get_partner_users(1, user_svc)
        assert [u.id for u in partners] == [2]

    def test_get_incoming_request_count(self, db_path, make_user):
        make_user(1, 2, 3)
        svc = DataShareService(db_path)
        assert svc.get_incoming_request_count(1) == 0
        svc.send_request(2, 1)
        svc.send_request(3, 1)
        assert svc.get_incoming_request_count(1) == 2

    def test_get_local_user_id(self, db_path, make_user):
        user_svc = make_user(1)
        user_svc.upsert(user_id=1, appuser_id=4242, gym_id=1, display_name="One")
        svc = DataShareService(db_path)
        assert svc.get_local_user_id(4242) == 1
        assert svc.get_local_user_id(9999) is None

    def test_get_share_statuses_for_friends(self, db_path, make_user):
        user_svc = make_user(1, 2)
        user_svc.upsert(user_id=2, appuser_id=202, gym_id=2, display_name="Two")
        svc = DataShareService(db_path)
        svc.send_request(1, 2)
        statuses = svc.get_share_statuses_for_friends(1, [202])
        assert statuses[202] == "pending_outgoing"

    def test_send_request_reverse_direction(self, db_path, make_user):
        make_user(1, 2)
        svc = DataShareService(db_path)
        svc.send_request(2, 1)
        assert svc.get_share_status(1, 2) == "pending_incoming"
        assert svc.get_share_status(2, 1) == "pending_outgoing"

    def test_revoked_share_can_be_re_requested(self, db_path, make_user):
        make_user(1, 2)
        svc = DataShareService(db_path)
        svc.send_request(1, 2)
        svc.accept_request(2, 1)
        svc.revoke_share(1, 2)
        assert svc.send_request(1, 2) is True
        assert svc.get_share_status(1, 2) == "pending_outgoing"

    def test_non_partner_cannot_send_request_to_self(self, db_path, make_user):
        make_user(1)
        svc = DataShareService(db_path)
        assert svc.send_request(1, 1) is False

    def test_get_display_name(self, db_path, make_user):
        make_user(1)
        UserService(db_path).upsert(user_id=1, appuser_id=None, gym_id=1, display_name="Alice")
        svc = DataShareService(db_path)
        assert svc.get_display_name(1) == "Alice"
        assert svc.get_display_name(999) is None