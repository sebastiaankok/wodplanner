"""User model."""

from datetime import datetime

from pydantic import BaseModel


class User(BaseModel):
    id: int
    appuser_id: int | None = None
    gym_id: int | None = None
    display_name: str | None = None
    avatar_filename: str | None = None
    tracking_disabled: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
