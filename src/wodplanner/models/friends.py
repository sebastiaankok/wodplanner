"""Friends models."""

from datetime import datetime

from pydantic import BaseModel


class Friend(BaseModel):
    """A friend to track in the calendar."""

    id: int | None = None
    owner_user_id: int  # WodApp user_id of the session owner
    appuser_id: int  # WodApp user ID of the friend
    name: str
    added_at: datetime | None = None
