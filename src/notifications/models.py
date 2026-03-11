"""Data models for notifications.

Notifications are time-limited messages that overlay the current board
display. They move through a lifecycle: queued → displayed → expired.
"""

from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field
import uuid


class Notification(BaseModel):
    """A notification that can be displayed on the board."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    message: str = Field(min_length=1, max_length=132)
    status: str = Field(default="queued")  # queued, displayed, expired
    priority: int = Field(default=0, ge=0, le=10)
    duration_seconds: int = Field(default=30, ge=5, le=3600)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    displayed_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None

    def validate_config(self) -> List[str]:
        errors: List[str] = []
        if self.status not in ("queued", "displayed", "expired"):
            errors.append(f"Invalid status: {self.status}")
        if not self.message or not self.message.strip():
            errors.append("Message cannot be empty")
        return errors

    def is_valid(self) -> bool:
        return len(self.validate_config()) == 0

    def is_expired(self) -> bool:
        """Check if a displayed notification has exceeded its duration."""
        if self.status != "displayed" or self.displayed_at is None:
            return False
        elapsed = (datetime.now(timezone.utc) - self.displayed_at).total_seconds()
        return elapsed >= self.duration_seconds


class NotificationCreate(BaseModel):
    """Request model for creating a new notification."""

    message: str = Field(min_length=1, max_length=132)
    priority: int = Field(default=0, ge=0, le=10)
    duration_seconds: int = Field(default=30, ge=5, le=3600)


VALID_STATUSES = ("queued", "displayed", "expired")
