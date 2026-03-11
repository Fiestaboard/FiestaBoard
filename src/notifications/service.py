"""Notification service for CRUD and queue management."""

import logging
from typing import List, Optional
from datetime import datetime, timezone

from .models import Notification, NotificationCreate
from .storage import NotificationStorage

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for notification operations.

    Handles CRUD, queue management, and lifecycle transitions
    (queued → displayed → expired).
    """

    def __init__(self, storage: Optional[NotificationStorage] = None):
        self.storage = storage or NotificationStorage()
        logger.info("NotificationService initialized")

    def list_notifications(self) -> List[Notification]:
        return self.storage.list_all()

    def get_notification(self, notification_id: str) -> Optional[Notification]:
        return self.storage.get(notification_id)

    def create_notification(self, data: NotificationCreate) -> Notification:
        notification = Notification(
            message=data.message,
            priority=data.priority,
            duration_seconds=data.duration_seconds,
            status="queued",
            created_at=datetime.now(timezone.utc),
        )
        return self.storage.create(notification)

    def delete_notification(self, notification_id: str) -> bool:
        return self.storage.delete(notification_id)

    def get_queued(self) -> List[Notification]:
        """Return queued notifications ordered by priority (highest first), then creation time."""
        all_notifs = self.storage.list_all()
        queued = [n for n in all_notifs if n.status == "queued"]
        queued.sort(key=lambda n: (-n.priority, n.created_at))
        return queued

    def get_displayed(self) -> List[Notification]:
        """Return currently displayed notifications."""
        return [n for n in self.storage.list_all() if n.status == "displayed"]

    def get_history(self) -> List[Notification]:
        """Return expired/displayed notifications sorted by most recent first."""
        all_notifs = self.storage.list_all()
        return [n for n in all_notifs if n.status in ("displayed", "expired")]

    def mark_displayed(self, notification_id: str) -> Optional[Notification]:
        """Transition a notification from queued to displayed."""
        return self.storage.update(notification_id, {
            "status": "displayed",
            "displayed_at": datetime.now(timezone.utc),
        })

    def mark_expired(self, notification_id: str) -> Optional[Notification]:
        """Transition a notification from displayed to expired."""
        return self.storage.update(notification_id, {
            "status": "expired",
            "expired_at": datetime.now(timezone.utc),
        })

    def expire_overdue(self) -> List[str]:
        """Expire any displayed notifications that have exceeded their duration.

        Returns a list of notification IDs that were expired.
        """
        expired_ids = []
        for n in self.get_displayed():
            if n.is_expired():
                self.mark_expired(n.id)
                expired_ids.append(n.id)
        return expired_ids

    def next_notification(self) -> Optional[Notification]:
        """Get the next notification to display (highest priority queued).

        Automatically expires any overdue displayed notifications first,
        then returns the next queued notification if no notification is
        currently being displayed.
        """
        self.expire_overdue()

        # If something is currently displayed and not expired, wait
        currently_displayed = self.get_displayed()
        if currently_displayed:
            return None

        queued = self.get_queued()
        if not queued:
            return None

        return queued[0]


_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
