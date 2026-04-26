"""WodApp API client for interacting with ws.paynplan.nl."""

import logging
import random
import time
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, cast

import httpx

from wodplanner.models.auth import AuthSession, LoginResponse
from wodplanner.models.calendar import (
    Appointment,
    AppointmentDetails,
    Member,
    SubscribeResponse,
    Subscriptions,
    WaitingList,
)
from wodplanner.utils.dates import fmt_api_datetime, parse_iso_datetime

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from wodplanner.services.api_cache import ApiCacheService


class WodAppError(Exception):
    """Base exception for WodApp API errors."""

    pass


class AuthenticationError(WodAppError):
    """Raised when authentication fails."""

    pass


class WodAppClient:
    """Client for the WodApp API (ws.paynplan.nl)."""

    BASE_URL = "https://ws.paynplan.nl/"
    APP = "wodapp"
    VERSION = "14.0"
    LANGUAGE = "nl_NL"
    CLIENT_USER_AGENT = "browser"

    def __init__(self) -> None:
        self._client = httpx.Client(timeout=30.0)
        self._session: AuthSession | None = None
        self._cache: "ApiCacheService | None" = None

    @classmethod
    def from_session(cls, session: AuthSession, cache: "ApiCacheService | None" = None) -> "WodAppClient":
        """
        Create a pre-authenticated client from an existing session.

        Args:
            session: An AuthSession with valid token and user info
            cache: Optional cache service for non-user-specific data

        Returns:
            WodAppClient ready to make authenticated requests
        """
        client = cls()
        client._session = session
        client._cache = cache
        return client

    def __enter__(self) -> "WodAppClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    @property
    def session(self) -> AuthSession:
        """Get the current authenticated session."""
        if self._session is None:
            raise AuthenticationError("Not logged in. Call login() first.")
        return self._session

    @property
    def is_authenticated(self) -> bool:
        """Check if client is authenticated."""
        return self._session is not None

    def _base_params(self) -> dict[str, str]:
        """Get base parameters for all requests."""
        return {
            "data[app]": self.APP,
            "data[language]": self.LANGUAGE,
            "data[version]": self.VERSION,
            "data[clientUserAgent]": self.CLIENT_USER_AGENT,
        }

    def _auth_params(self) -> dict[str, str]:
        """Get authentication parameters for authenticated requests."""
        return {
            "data[token]": self.session.token,
            "data[id_appuser_li]": str(self.session.user_id),
            "data[id_gym]": str(self.session.gym_id),
            "data[idc]": str(self.session.gym_id),
        }

    _RETRY_STATUSES = {502, 503, 504}
    _MAX_RETRIES = 2

    def _request(self, params: dict[str, str]) -> dict[str, Any]:
        """Make a POST request to the API."""
        user = (
            f"user:{self._session.user_id} ({self._session.firstname})"
            if self._session
            else "unauthenticated"
        )
        logger.info(
            "%s → %s.%s",
            user,
            params.get("data[service]", "?"),
            params.get("data[method]", "?"),
        )
        response = None
        for attempt in range(self._MAX_RETRIES + 1):
            try:
                response = self._client.post(
                    self.BASE_URL,
                    data=params,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
                break
            except httpx.HTTPStatusError as e:
                if e.response.status_code in self._RETRY_STATUSES and attempt < self._MAX_RETRIES:
                    time.sleep(2**attempt + random.uniform(0, 1))
                    continue
                if e.response.status_code in self._RETRY_STATUSES:
                    raise WodAppError("WodApp service is temporarily unavailable. Please try again later.")
                raise WodAppError(f"API request failed with status {e.response.status_code}")
            except httpx.TransportError as e:
                raise WodAppError(f"Cannot reach WodApp service: {e}")
        assert response is not None
        data = response.json()

        if data.get("status") != "OK":
            notice = data.get("notice", "Unknown error")
            raise WodAppError(f"API error: {notice}")

        return cast("dict[str, Any]", data)

    def _request_typed(self, params: dict[str, str]) -> dict[str, Any]:
        return self._request(params)

    def login(self, username: str, password: str) -> AuthSession:
        """
        Authenticate with the WodApp API.

        Args:
            username: Email address
            password: Password

        Returns:
            AuthSession with token and user info
        """
        params = {
            **self._base_params(),
            "data[service]": "user",
            "data[method]": "login",
            "data[username]": username,
            "data[pass]": password,
            "data[gcl]": "1",
            "data[id_appuser_li]": "",
        }

        data = self._request(params)
        login_resp = LoginResponse(**data)

        if not login_resp.gyms:
            raise AuthenticationError("No gyms associated with account")

        gym = login_resp.gyms[0]
        self._session = AuthSession(
            token=login_resp.token,
            user_id=login_resp.id_user,
            appuser_id=login_resp.id_appuser,
            username=login_resp.username,
            firstname=login_resp.firstname,
            gym_id=gym.id_gym,
            gym_name=gym.name,
        )

        # Fetch agenda ID
        self._fetch_agenda_id()

        return self._session

    def _fetch_agenda_id(self) -> None:
        """Fetch and set the agenda ID for the gym."""
        params = {
            **self._base_params(),
            **self._auth_params(),
            "data[service]": "agenda",
            "data[method]": "getAgendas",
        }

        data = self._request(params)
        agendas = data.get("resultset", [])

        if agendas:
            sess = self._session
            assert sess is not None
            sess.agenda_id = agendas[0].get("id_agenda")

    def get_day_schedule(self, day: date | None = None) -> list[Appointment]:
        """
        Get the schedule for a specific day.

        Args:
            day: Date to fetch schedule for (defaults to today)

        Returns:
            List of appointments for the day
        """
        if day is None:
            day = date.today()

        params = {
            **self._base_params(),
            **self._auth_params(),
            "data[service]": "agenda",
            "data[method]": "day",
            "data[type]": "gym",
            "data[id_agenda]": str(self.session.agenda_id),
            "data[dateInfo][date]": day.isoformat(),
        }

        data = self._request(params)

        appointments = []
        for item in data.get("resultset", []):
            appointments.append(
                Appointment(
                    id_appointment=item["id_appointment"],
                    id_appointment_type=item["id_appointment_type"],
                    id_parent=item["id_parent"],
                    name=item["name"],
                    date_start=parse_iso_datetime(item["date_start"]),
                    date_end=parse_iso_datetime(item["date_end"]),
                    max_subscriptions=item["max_subscriptions"],
                    total_subscriptions=item["total_subscriptions"],
                    status=item["status"],
                    location=item.get("location", ""),
                    description=item.get("description", ""),
                    employee_name=item.get("employee_name", ""),
                )
            )

        return appointments

    def get_appointment_details(
        self,
        appointment_id: int,
        date_start: datetime,
        date_end: datetime,
    ) -> AppointmentDetails:
        """
        Get detailed info about an appointment including participants.

        Args:
            appointment_id: The appointment ID
            date_start: Start datetime of the appointment
            date_end: End datetime of the appointment

        Returns:
            AppointmentDetails with full info including member list
        """
        params = {
            **self._base_params(),
            **self._auth_params(),
            "data[service]": "agenda",
            "data[method]": "appointment",
            "data[id_agenda]": str(self.session.agenda_id),
            "data[id]": str(appointment_id),
            "data[date_start]": fmt_api_datetime(date_start),
            "data[date_end]": fmt_api_datetime(date_end),
        }

        data = self._request(params)
        result = data["resultset"]

        # Parse subscriptions
        subs_data = result.get("subscriptions", {})
        subscriptions = Subscriptions(
            subscribed=subs_data.get("subscribed", 0),
            total=subs_data.get("total", 0),
            full=subs_data.get("full", 0),
            members=[Member(**m) for m in subs_data.get("members", [])],
        )

        # Parse waiting list
        wl_data = result.get("waitinglist", {})
        waitinglist = WaitingList(
            total=wl_data.get("total", 0),
            members=[Member(**m) for m in wl_data.get("members", [])],
        )

        return AppointmentDetails(
            id_appointment=result["id_appointment"],
            id_appointment_type=result["id_appointment_type"],
            name=result["name"],
            date_start=parse_iso_datetime(result["date_start"]),
            date_end=parse_iso_datetime(result["date_end"]),
            max_subscriptions=result["max_subscriptions"],
            waiting_list=result.get("waiting_list", 0),
            number_hours_before_subscription_opens=result.get(
                "number_hours_before_subscription_opens", 168
            ),
            subscription_open_date=result.get("subscription_open_date", ""),
            subscribe_not_opened_yet=result.get("subscribe_not_opened_yet", 0),
            subscribe_closed=result.get("subscribe_closed", 0),
            unsubscribe_closed=result.get("unsubscribe_closed", 0),
            subscriptions=subscriptions,
            waitinglist=waitinglist,
            location=result.get("location", ""),
            description=result.get("description", ""),
            employee_name=result.get("employee_name", ""),
        )

    def _subscription_request(
        self,
        method: str,
        action: str,
        id_appointment: int,
        date_start: datetime,
        date_end: datetime,
    ) -> SubscribeResponse:
        params = {
            **self._base_params(),
            **self._auth_params(),
            "data[service]": "agenda",
            "data[method]": method,
            "data[id_agenda]": str(self.session.agenda_id),
            "data[id]": str(id_appointment),
            "data[date_start_org]": fmt_api_datetime(date_start),
            "data[date_end_org]": fmt_api_datetime(date_end),
            "data[action]": action,
        }
        data = self._request(params)
        return SubscribeResponse(
            status=data["status"],
            notice=data.get("notice", ""),
            subscribedWithSuccess=data.get("subscribedWithSuccess", 0),
        )

    def subscribe(self, appointment_id: int, date_start: datetime, date_end: datetime) -> SubscribeResponse:
        """Subscribe to an appointment."""
        return self._subscription_request("subscribeAppointment", "subscribe", appointment_id, date_start, date_end)

    def unsubscribe(self, appointment_id: int, date_start: datetime, date_end: datetime) -> SubscribeResponse:
        """Unsubscribe from an appointment."""
        return self._subscription_request("subscribeAppointment", "unsubscribe", appointment_id, date_start, date_end)

    def subscribe_waitinglist(self, appointment_id: int, date_start: datetime, date_end: datetime) -> SubscribeResponse:
        """Subscribe to an appointment's waiting list."""
        return self._subscription_request("subscribeWaitingList", "subscribe", appointment_id, date_start, date_end)

    def unsubscribe_waitinglist(self, appointment_id: int, date_start: datetime, date_end: datetime) -> SubscribeResponse:
        """Unsubscribe from an appointment's waiting list."""
        return self._subscription_request("subscribeWaitingList", "unsubscribe", appointment_id, date_start, date_end)

    def get_upcoming_reservations(self) -> tuple[list[dict], dict]:
        """
        Get upcoming reservations for the current user.

        Returns:
            Tuple of (list of dicts with id_appointment, name, date_start (datetime), sorted by date, company_images)
        """
        params = {
            **self._base_params(),
            **self._auth_params(),
            "data[service]": "gym",
            "data[method]": "getModulesEnabledGym",
            "data[companyImages]": "1",
            "data[numberOutstandingInvoices]": "0",
            "data[id_gym_group]": str(self.session.gym_id),
            "data[gyms][0]": str(self.session.gym_id),
        }

        data = self._request(params)
        reservations = data.get("widgets", {}).get("reservations", {})
        company_images = data.get("companyImages", {})

        result = []
        for r in reservations.get("data", []):
            dt = datetime.strptime(r["date_start"], "%d-%m-%Y %H:%M")
            result.append({
                "id_appointment": r["id_appointment"],
                "name": r["name"],
                "date_start": dt,
            })

        result.sort(key=lambda x: x["date_start"])
        return result, company_images

    def get_appointment_members(
        self,
        appointment_id: int,
        date_start: datetime,
        date_end: datetime,
        expected_total: int | None = None,
    ) -> tuple[list[Member], WaitingList]:
        """Return subscribed members and waiting list. Cached when ApiCacheService is available."""
        cache_key = f"{self.session.agenda_id}:{appointment_id}:{date_start.isoformat()}:{date_end.isoformat()}"

        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                cached_members, cached_wl = cast("tuple[list[Member], WaitingList]", cached)
                # If we have an expected total, check if the cached member list matches it
                if expected_total is not None and len(cached_members) != expected_total:
                    logger.debug("Cache stale (count mismatch): %s", cache_key)
                    self._cache.invalidate(cache_key)
                else:
                    return cached_members, cached_wl

        details = self.get_appointment_details(appointment_id, date_start, date_end)
        result = (details.subscriptions.members, details.waitinglist)

        if self._cache:
            self._cache.set(cache_key, result)
            logger.debug("Cache set: %s", cache_key)

        return result

    def find_friends_in_appointments(
        self,
        friend_ids: set[int],
        day: date | None = None,
    ) -> dict[int, list[Member]]:
        """
        Find which friends are signed up for appointments on a given day.

        Args:
            friend_ids: Set of friend user IDs to look for
            day: Date to check (defaults to today)

        Returns:
            Dict mapping appointment_id to list of friends found
        """
        if day is None:
            day = date.today()

        appointments = self.get_day_schedule(day)
        result: dict[int, list[Member]] = {}

        for appt in appointments:
            members, _ = self.get_appointment_members(
                appt.id_appointment,
                appt.date_start,
                appt.date_end,
                expected_total=appt.total_subscriptions,
            )

            friends_found = [m for m in members if m.id_appuser in friend_ids]

            if friends_found:
                result[appt.id_appointment] = friends_found

        return result
