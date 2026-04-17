"""Friends models."""

from datetime import datetime

from pydantic import BaseModel


class Friend(BaseModel):
    """A friend to track in the calendar."""

    id: int | None = None
    appuser_id: int  # WodApp user ID
    name: str  # Display name
    added_at: datetime | None = None
