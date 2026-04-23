"""Calendar and appointment models."""

from datetime import datetime

from pydantic import BaseModel, Field


class Appointment(BaseModel):
    """Appointment from day schedule."""

    id_appointment: int
    id_appointment_type: int
    id_parent: int | None = None
    name: str
    date_start: datetime
    date_end: datetime
    max_subscriptions: int
    total_subscriptions: int
    status: str  # "open", "closed", "subscribed"
    location: str = ""
    description: str = ""
    employee_name: str = ""


class DaySchedule(BaseModel):
    """Response from agenda.day API call."""

    status: str
    notice: str = ""
    resultset: list[Appointment]


class Member(BaseModel):
    """A member subscribed to an appointment."""

    name: str
    id_appuser: int
    id_partner: int = 0
    imageURL: str = Field(default="", alias="imageURL")


class Subscriptions(BaseModel):
    """Subscription info for an appointment."""

    subscribed: int  # 1 if current user is subscribed
    total: int
    full: int
    members: list[Member]


class WaitingList(BaseModel):
    """Waiting list info for an appointment."""

    total: int
    members: list[Member]


class AppointmentDetails(BaseModel):
    """Detailed appointment info from agenda.appointment API call."""

    id_appointment: int
    id_appointment_type: int
    name: str
    date_start: datetime
    date_end: datetime
    max_subscriptions: int
    waiting_list: int  # 1 if waiting list enabled
    number_hours_before_subscription_opens: int
    subscription_open_date: str  # Format: "12-04-2026 11:00"
    subscribe_not_opened_yet: int  # 1 if not open yet
    subscribe_closed: int  # 1 if closed
    unsubscribe_closed: int
    subscriptions: Subscriptions
    waitinglist: WaitingList
    location: str = ""
    description: str = ""
    employee_name: str = ""

    def is_open_for_signup(self) -> bool:
        """Check if appointment is open for signup."""
        return self.subscribe_not_opened_yet == 0 and self.subscribe_closed == 0

    def has_spots_available(self) -> bool:
        """Check if there are spots available."""
        return self.subscriptions.total < self.max_subscriptions

    def is_user_subscribed(self) -> bool:
        """Check if current user is subscribed."""
        return self.subscriptions.subscribed == 1

    def get_member_ids(self) -> set[int]:
        """Get set of all subscribed member IDs."""
        return {m.id_appuser for m in self.subscriptions.members}


class SubscribeResponse(BaseModel):
    """Response from subscribe API calls."""

    status: str
    notice: str = ""
    subscribedWithSuccess: int = 0
