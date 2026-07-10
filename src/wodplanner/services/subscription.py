"""SubscriptionService — compose WodApp Sign Up."""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum

from wodplanner.api.client import WodAppClient

logger = logging.getLogger(__name__)


class SubscribeAction(str, Enum):
    SUBSCRIBE = "subscribe"
    WAITLIST = "waitinglist"
    UNSUBSCRIBE = "unsubscribe"
    UNSUBSCRIBE_WAITLIST = "unsubscribe_waitinglist"


class SubscriptionService:
    def __init__(self, client: WodAppClient) -> None:
        self._client = client

    def act(
        self,
        appointment_id: int,
        start: datetime,
        end: datetime,
        action: SubscribeAction,
    ) -> None:
        self._dispatch(appointment_id, start, end, action)

    def _dispatch(
        self,
        appointment_id: int,
        start: datetime,
        end: datetime,
        action: SubscribeAction,
    ) -> None:
        dispatch_map = {
            SubscribeAction.SUBSCRIBE: self._client.subscribe,
            SubscribeAction.WAITLIST: self._client.subscribe_waitinglist,
            SubscribeAction.UNSUBSCRIBE: self._client.unsubscribe,
            SubscribeAction.UNSUBSCRIBE_WAITLIST: self._client.unsubscribe_waitinglist,
        }
        handler = dispatch_map[action]
        handler(appointment_id, start, end)