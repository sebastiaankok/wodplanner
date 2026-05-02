"""Tests for SubscriptionService — compose Sign Up + Google Calendar Sync."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from wodplanner.api.client import WodAppClient
from wodplanner.models.auth import AuthSession


class TestSubscribeActionDispatch:
    """Each SubscribeAction dispatches the correct WodAppClient method."""

    @pytest.fixture
    def client(self):
        return MagicMock(spec=WodAppClient)

    @pytest.fixture
    def background_tasks(self):
        bt = MagicMock()
        # Prevent real task scheduling side effects
        bt.add_task = MagicMock()
        return bt

    @pytest.fixture
    def google_db(self):
        db = MagicMock()
        db.get_account.return_value = None  # no sync account
        return db

    @pytest.fixture
    def sync_service(self):
        return MagicMock()

    def test_subscribe_action(self, client, background_tasks, google_db, sync_service):
        from wodplanner.services.subscription import SubscribeAction, SubscriptionService

        service = SubscriptionService(
            client=client,
            google_db=google_db,
            sync_service=sync_service,
        )
        start = datetime(2026, 4, 25, 10, 0)
        end = datetime(2026, 4, 25, 11, 0)

        service.act(appointment_id=1, start=start, end=end, action=SubscribeAction.SUBSCRIBE, background_tasks=background_tasks)

        client.subscribe.assert_called_once_with(1, start, end)
        # No sync account -> no enqueue
        background_tasks.add_task.assert_not_called()

    def test_waitinglist_action(self, client, background_tasks, google_db, sync_service):
        from wodplanner.services.subscription import SubscribeAction, SubscriptionService

        service = SubscriptionService(
            client=client,
            google_db=google_db,
            sync_service=sync_service,
        )
        start = datetime(2026, 4, 25, 10, 0)
        end = datetime(2026, 4, 25, 11, 0)

        service.act(appointment_id=1, start=start, end=end, action=SubscribeAction.WAITLIST, background_tasks=background_tasks)

        client.subscribe_waitinglist.assert_called_once_with(1, start, end)
        background_tasks.add_task.assert_not_called()

    def test_unsubscribe_action(self, client, background_tasks, google_db, sync_service):
        from wodplanner.services.subscription import SubscribeAction, SubscriptionService

        service = SubscriptionService(
            client=client,
            google_db=google_db,
            sync_service=sync_service,
        )
        start = datetime(2026, 4, 25, 10, 0)
        end = datetime(2026, 4, 25, 11, 0)

        service.act(appointment_id=1, start=start, end=end, action=SubscribeAction.UNSUBSCRIBE, background_tasks=background_tasks)

        client.unsubscribe.assert_called_once_with(1, start, end)
        background_tasks.add_task.assert_not_called()

    def test_unsubscribe_waitinglist_action(self, client, background_tasks, google_db, sync_service):
        from wodplanner.services.subscription import SubscribeAction, SubscriptionService

        service = SubscriptionService(
            client=client,
            google_db=google_db,
            sync_service=sync_service,
        )
        start = datetime(2026, 4, 25, 10, 0)
        end = datetime(2026, 4, 25, 11, 0)

        service.act(appointment_id=1, start=start, end=end, action=SubscribeAction.UNSUBSCRIBE_WAITLIST, background_tasks=background_tasks)

        client.unsubscribe_waitinglist.assert_called_once_with(1, start, end)
        background_tasks.add_task.assert_not_called()


class TestSyncEnqueue:
    """Calendar sync is enqueued exactly once when account exists and enabled."""

    @pytest.fixture
    def client(self):
        return MagicMock(spec=WodAppClient)

    @pytest.fixture
    def background_tasks(self):
        bt = MagicMock()
        bt.add_task = MagicMock()
        return bt

    @pytest.fixture
    def sync_account(self, auth_session):
        """Mock GoogleAccount with sync enabled."""
        account = MagicMock()
        account.sync_enabled = True
        account.calendar_id = "primary"
        return account

    @pytest.fixture
    def google_db(self, sync_account):
        db = MagicMock()
        db.get_account.return_value = sync_account
        return db

    @pytest.fixture
    def auth_session(self) -> AuthSession:
        return AuthSession(
            token="test_token",
            user_id=42,
            appuser_id=4242,
            username="user@example.com",
            firstname="User",
            gym_id=100,
            gym_name="Test Gym",
            agenda_id=5,
        )

    def test_sync_enqueued_when_account_enabled(self, client, background_tasks, google_db, auth_session):
        from wodplanner.services.subscription import SubscribeAction, SubscriptionService

        service = SubscriptionService(
            client=client,
            google_db=google_db,
            sync_service=MagicMock(),
        )
        start = datetime(2026, 4, 25, 10, 0)
        end = datetime(2026, 4, 25, 11, 0)

        service.act(appointment_id=1, start=start, end=end, action=SubscribeAction.SUBSCRIBE, background_tasks=background_tasks, session=auth_session)

        # Verify sync was enqueued exactly once
        background_tasks.add_task.assert_called_once()

    def test_sync_not_enqueued_when_account_disabled(self, client, background_tasks, google_db, auth_session):
        from wodplanner.services.subscription import SubscribeAction, SubscriptionService

        google_db.get_account.return_value.sync_enabled = False

        service = SubscriptionService(
            client=client,
            google_db=google_db,
            sync_service=MagicMock(),
        )
        start = datetime(2026, 4, 25, 10, 0)
        end = datetime(2026, 4, 25, 11, 0)

        service.act(appointment_id=1, start=start, end=end, action=SubscribeAction.SUBSCRIBE, background_tasks=background_tasks, session=auth_session)

        client.subscribe.assert_called_once()
        background_tasks.add_task.assert_not_called()

    def test_sync_not_enqueued_when_no_account(self, client, background_tasks, google_db, auth_session):
        from wodplanner.services.subscription import SubscribeAction, SubscriptionService

        google_db.get_account.return_value = None

        service = SubscriptionService(
            client=client,
            google_db=google_db,
            sync_service=MagicMock(),
        )
        start = datetime(2026, 4, 25, 10, 0)
        end = datetime(2026, 4, 25, 11, 0)

        service.act(appointment_id=1, start=start, end=end, action=SubscribeAction.SUBSCRIBE, background_tasks=background_tasks, session=auth_session)

        client.subscribe.assert_called_once()
        background_tasks.add_task.assert_not_called()
