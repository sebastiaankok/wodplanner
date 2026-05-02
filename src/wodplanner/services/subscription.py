"""SubscriptionService — compose WodApp Sign Up + Google Calendar Sync."""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from fastapi import BackgroundTasks

from wodplanner.api.client import WodAppClient

if TYPE_CHECKING:
    from wodplanner.models.auth import AuthSession
    from wodplanner.services.calendar_sync import CalendarSyncService
    from wodplanner.services.google_accounts import GoogleAccountsService


logger = logging.getLogger(__name__)


class SubscribeAction(str, Enum):
    SUBSCRIBE = "subscribe"
    WAITLIST = "waitinglist"
    UNSUBSCRIBE = "unsubscribe"
    UNSUBSCRIBE_WAITLIST = "unsubscribe_waitinglist"


class SubscriptionService:
    """Composes WodApp subscription API call + Google Calendar sync enqueue."""

    def __init__(
        self,
        client: WodAppClient,
        google_db: GoogleAccountsService,
        sync_service: CalendarSyncService,
    ) -> None:
        self._client = client
        self._google_db = google_db
        self._sync_service = sync_service

    def act(
        self,
        appointment_id: int,
        start: datetime,
        end: datetime,
        action: SubscribeAction,
        background_tasks: BackgroundTasks,
        session: AuthSession | None = None,
    ) -> None:
        """Execute subscription action and enqueue calendar sync if applicable."""
        self._dispatch(appointment_id, start, end, action)
        if session:
            self._enqueue_sync(background_tasks, session)

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

    def _enqueue_sync(
        self,
        background_tasks: BackgroundTasks,
        session: AuthSession,
    ) -> None:
        account = self._google_db.get_account(session.user_id)
        if not account or not account.sync_enabled or not account.calendar_id:
            return
        background_tasks.add_task(
            self._sync_service.sync,
            account=account,
            client=self._client,
            first_name=session.firstname,
            gym_name=session.gym_name,
            gym_id=session.gym_id,
        )
