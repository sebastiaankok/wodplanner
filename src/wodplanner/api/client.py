"""WodApp API client for interacting with ws.paynplan.nl."""

from datetime import date, datetime
from typing import Any

import httpx

from wodplanner.models.auth import AuthSession, LoginResponse
from wodplanner.models.calendar import (
    Appointment,
    AppointmentDetails,
    DaySchedule,
    Member,
    SubscribeResponse,
    Subscriptions,
    WaitingList,
)


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

    @classmethod
    def from_session(cls, session: AuthSession) -> "WodAppClient":
        """
        Create a pre-authenticated client from an existing session.

        Args:
            session: An AuthSession with valid token and user info

        Returns:
            WodAppClient ready to make authenticated requests
        """
        client = cls()
        client._session = session
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

    def _request(self, params: dict[str, str]) -> dict[str, Any]:
        """Make a POST request to the API."""
        response = self._client.post(
            self.BASE_URL,
            data=params,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "OK":
            notice = data.get("notice", "Unknown error")
            raise WodAppError(f"API error: {notice}")

        return data

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
            self._session.agenda_id = agendas[0].get("id_agenda")

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
                    date_start=datetime.fromisoformat(item["date_start"]),
                    date_end=datetime.fromisoformat(item["date_end"]),
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
            "data[date_start]": date_start.strftime("%Y-%m-%d %H:%M"),
            "data[date_end]": date_end.strftime("%Y-%m-%d %H:%M"),
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
            date_start=datetime.fromisoformat(result["date_start"]),
            date_end=datetime.fromisoformat(result["date_end"]),
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

    def subscribe(
        self,
        appointment_id: int,
        date_start: datetime,
        date_end: datetime,
    ) -> SubscribeResponse:
        """
        Subscribe to an appointment.

        Args:
            appointment_id: The appointment ID
            date_start: Start datetime of the appointment
            date_end: End datetime of the appointment

        Returns:
            SubscribeResponse with success status
        """
        params = {
            **self._base_params(),
            **self._auth_params(),
            "data[service]": "agenda",
            "data[method]": "subscribeAppointment",
            "data[id_agenda]": str(self.session.agenda_id),
            "data[id]": str(appointment_id),
            "data[date_start_org]": date_start.strftime("%Y-%m-%d %H:%M"),
            "data[date_end_org]": date_end.strftime("%Y-%m-%d %H:%M"),
            "data[action]": "subscribe",
        }

        data = self._request(params)
        return SubscribeResponse(
            status=data["status"],
            notice=data.get("notice", ""),
            subscribedWithSuccess=data.get("subscribedWithSuccess", 0),
        )

    def unsubscribe(
        self,
        appointment_id: int,
        date_start: datetime,
        date_end: datetime,
    ) -> SubscribeResponse:
        """
        Unsubscribe from an appointment.

        Args:
            appointment_id: The appointment ID
            date_start: Start datetime of the appointment
            date_end: End datetime of the appointment

        Returns:
            SubscribeResponse with success status
        """
        params = {
            **self._base_params(),
            **self._auth_params(),
            "data[service]": "agenda",
            "data[method]": "subscribeAppointment",
            "data[id_agenda]": str(self.session.agenda_id),
            "data[id]": str(appointment_id),
            "data[date_start_org]": date_start.strftime("%Y-%m-%d %H:%M"),
            "data[date_end_org]": date_end.strftime("%Y-%m-%d %H:%M"),
            "data[action]": "unsubscribe",
        }

        data = self._request(params)
        return SubscribeResponse(
            status=data["status"],
            notice=data.get("notice", ""),
            subscribedWithSuccess=data.get("subscribedWithSuccess", 0),
        )

    def unsubscribe_waitinglist(
        self,
        appointment_id: int,
        date_start: datetime,
        date_end: datetime,
    ) -> SubscribeResponse:
        """
        Unsubscribe from an appointment's waiting list.

        Args:
            appointment_id: The appointment ID
            date_start: Start datetime of the appointment
            date_end: End datetime of the appointment

        Returns:
            SubscribeResponse with success status
        """
        params = {
            **self._base_params(),
            **self._auth_params(),
            "data[service]": "agenda",
            "data[method]": "subscribeWaitingList",
            "data[id_agenda]": str(self.session.agenda_id),
            "data[id]": str(appointment_id),
            "data[date_start_org]": date_start.strftime("%Y-%m-%d %H:%M"),
            "data[date_end_org]": date_end.strftime("%Y-%m-%d %H:%M"),
            "data[action]": "unsubscribe",
        }

        data = self._request(params)
        return SubscribeResponse(
            status=data["status"],
            notice=data.get("notice", ""),
            subscribedWithSuccess=data.get("subscribedWithSuccess", 0),
        )

    def subscribe_waitinglist(
        self,
        appointment_id: int,
        date_start: datetime,
        date_end: datetime,
    ) -> SubscribeResponse:
        """
        Subscribe to an appointment's waiting list.

        Args:
            appointment_id: The appointment ID
            date_start: Start datetime of the appointment
            date_end: End datetime of the appointment

        Returns:
            SubscribeResponse with success status
        """
        params = {
            **self._base_params(),
            **self._auth_params(),
            "data[service]": "agenda",
            "data[method]": "subscribeWaitingList",
            "data[id_agenda]": str(self.session.agenda_id),
            "data[id]": str(appointment_id),
            "data[date_start_org]": date_start.strftime("%Y-%m-%d %H:%M"),
            "data[date_end_org]": date_end.strftime("%Y-%m-%d %H:%M"),
            "data[action]": "subscribe",
        }

        data = self._request(params)
        return SubscribeResponse(
            status=data["status"],
            notice=data.get("notice", ""),
        )

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
            details = self.get_appointment_details(
                appt.id_appointment,
                appt.date_start,
                appt.date_end,
            )

            friends_found = [
                m for m in details.subscriptions.members if m.id_appuser in friend_ids
            ]

            if friends_found:
                result[appt.id_appointment] = friends_found

        return result
