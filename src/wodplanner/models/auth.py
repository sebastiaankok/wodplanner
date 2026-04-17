"""Authentication models."""

from pydantic import BaseModel


class Gym(BaseModel):
    """Gym information from login response."""

    id_gym: int
    idc: int
    name: str
    city: str
    unsubscribed_for_mailing: int = 0


class LoginResponse(BaseModel):
    """Response from user.login API call."""

    status: str
    notice: str = ""
    id_user: int
    username: str
    firstname: str
    token: str
    gyms: list[Gym]


class AuthSession(BaseModel):
    """Authenticated session data for making API requests."""

    token: str
    user_id: int
    username: str
    firstname: str
    gym_id: int
    gym_name: str
    agenda_id: int | None = None
