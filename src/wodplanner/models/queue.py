"""Queue models for auto-signup feature."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class QueueStatus(str, Enum):
    """Status of a queued signup."""

    PENDING = "pending"  # Waiting for signup time
    SCHEDULED = "scheduled"  # Job scheduled with APScheduler
    COMPLETED = "completed"  # Successfully signed up
    FAILED = "failed"  # Signup failed
    WAITLISTED = "waitlisted"  # Added to waiting list (class was full)
    CANCELLED = "cancelled"  # User cancelled


class QueuedSignup(BaseModel):
    """A queued auto-signup request."""

    id: int | None = None
    appointment_id: int
    appointment_name: str
    date_start: datetime
    date_end: datetime
    signup_opens_at: datetime
    status: QueueStatus = QueueStatus.PENDING
    result_message: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    # User authentication for scheduled signups
    user_token: str | None = None
    user_id: int | None = None

    class Config:
        use_enum_values = True
