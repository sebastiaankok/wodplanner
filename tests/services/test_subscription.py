"""Tests for SubscriptionService — compose Sign Up."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from wodplanner.api.client import WodAppClient


class TestSubscribeActionDispatch:
    """Each SubscribeAction dispatches the correct WodAppClient method."""

    @pytest.fixture
    def client(self):
        return MagicMock(spec=WodAppClient)

    @pytest.fixture
    def auth_session(self):
        return MagicMock()

    def test_subscribe_action(self, client, auth_session):
        from wodplanner.services.subscription import SubscribeAction, SubscriptionService

        service = SubscriptionService(client=client)
        start = datetime(2026, 4, 25, 10, 0)
        end = datetime(2026, 4, 25, 11, 0)

        service.act(appointment_id=1, start=start, end=end, action=SubscribeAction.SUBSCRIBE)

        client.subscribe.assert_called_once_with(1, start, end)

    def test_waitinglist_action(self, client, auth_session):
        from wodplanner.services.subscription import SubscribeAction, SubscriptionService

        service = SubscriptionService(client=client)
        start = datetime(2026, 4, 25, 10, 0)
        end = datetime(2026, 4, 25, 11, 0)

        service.act(appointment_id=1, start=start, end=end, action=SubscribeAction.WAITLIST)

        client.subscribe_waitinglist.assert_called_once_with(1, start, end)

    def test_unsubscribe_action(self, client, auth_session):
        from wodplanner.services.subscription import SubscribeAction, SubscriptionService

        service = SubscriptionService(client=client)
        start = datetime(2026, 4, 25, 10, 0)
        end = datetime(2026, 4, 25, 11, 0)

        service.act(appointment_id=1, start=start, end=end, action=SubscribeAction.UNSUBSCRIBE)

        client.unsubscribe.assert_called_once_with(1, start, end)

    def test_unsubscribe_waitinglist_action(self, client, auth_session):
        from wodplanner.services.subscription import SubscribeAction, SubscriptionService

        service = SubscriptionService(client=client)
        start = datetime(2026, 4, 25, 10, 0)
        end = datetime(2026, 4, 25, 11, 0)

        service.act(appointment_id=1, start=start, end=end, action=SubscribeAction.UNSUBSCRIBE_WAITLIST)

        client.unsubscribe_waitinglist.assert_called_once_with(1, start, end)