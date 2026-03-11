"""Tests for notifications module (models, storage, service)."""

import pytest
import tempfile
import os
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch

from src.notifications.models import (
    Notification,
    NotificationCreate,
    VALID_STATUSES,
)
from src.notifications.storage import NotificationStorage
from src.notifications.service import NotificationService


# =============================================================================
# Model Tests
# =============================================================================


class TestNotificationModels:
    """Tests for Notification and related models."""

    def test_notification_defaults(self):
        """A notification has sensible defaults."""
        n = Notification(message="Hello world")
        assert n.message == "Hello world"
        assert n.status == "queued"
        assert n.priority == 0
        assert n.duration_seconds == 30
        assert n.id  # auto-generated
        assert n.created_at is not None
        assert n.displayed_at is None
        assert n.expired_at is None

    def test_notification_valid(self):
        """A notification with a message is valid."""
        n = Notification(message="Test notification")
        assert n.is_valid()
        assert n.validate_config() == []

    def test_notification_invalid_status(self):
        """An invalid status produces validation errors."""
        n = Notification(message="Test")
        n.status = "invalid_status"
        errors = n.validate_config()
        assert any("status" in e.lower() for e in errors)

    def test_notification_priority_range(self):
        """Priority must be between 0 and 10."""
        n = Notification(message="Test", priority=5)
        assert n.is_valid()

        with pytest.raises(Exception):
            Notification(message="Test", priority=-1)

        with pytest.raises(Exception):
            Notification(message="Test", priority=11)

    def test_notification_is_expired_not_displayed(self):
        """A queued notification is never expired."""
        n = Notification(message="Test", status="queued")
        assert not n.is_expired()

    def test_notification_is_expired_recent(self):
        """A recently displayed notification is not expired."""
        n = Notification(
            message="Test",
            status="displayed",
            displayed_at=datetime.now(timezone.utc),
            duration_seconds=60,
        )
        assert not n.is_expired()

    def test_notification_is_expired_overdue(self):
        """A displayed notification past its duration is expired."""
        n = Notification(
            message="Test",
            status="displayed",
            displayed_at=datetime.now(timezone.utc) - timedelta(seconds=120),
            duration_seconds=30,
        )
        assert n.is_expired()

    def test_notification_create_model(self):
        """NotificationCreate has correct defaults."""
        nc = NotificationCreate(message="Hello")
        assert nc.message == "Hello"
        assert nc.priority == 0
        assert nc.duration_seconds == 30

    def test_valid_statuses(self):
        """VALID_STATUSES contains the expected values."""
        assert "queued" in VALID_STATUSES
        assert "displayed" in VALID_STATUSES
        assert "expired" in VALID_STATUSES


# =============================================================================
# Storage Tests
# =============================================================================


class TestNotificationStorage:
    """Tests for NotificationStorage."""

    def _make_storage(self, tmp_dir: str) -> NotificationStorage:
        path = os.path.join(tmp_dir, "notifications.json")
        return NotificationStorage(storage_file=path)

    def test_create_and_list(self):
        """Create a notification and list it."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = self._make_storage(tmp)
            n = Notification(message="Test notification")
            storage.create(n)

            all_notifs = storage.list_all()
            assert len(all_notifs) == 1
            assert all_notifs[0].message == "Test notification"

    def test_get_notification(self):
        """Get a specific notification by ID."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = self._make_storage(tmp)
            n = Notification(message="Find me")
            storage.create(n)

            found = storage.get(n.id)
            assert found is not None
            assert found.message == "Find me"

    def test_get_nonexistent(self):
        """Getting a nonexistent notification returns None."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = self._make_storage(tmp)
            assert storage.get("nonexistent") is None

    def test_update_notification(self):
        """Update a notification's fields."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = self._make_storage(tmp)
            n = Notification(message="Original")
            storage.create(n)

            updated = storage.update(n.id, {"status": "displayed"})
            assert updated is not None
            assert updated.status == "displayed"

    def test_update_nonexistent(self):
        """Updating a nonexistent notification returns None."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = self._make_storage(tmp)
            assert storage.update("nonexistent", {"status": "displayed"}) is None

    def test_delete_notification(self):
        """Delete a notification."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = self._make_storage(tmp)
            n = Notification(message="Delete me")
            storage.create(n)
            assert storage.delete(n.id)
            assert storage.get(n.id) is None

    def test_delete_nonexistent(self):
        """Deleting a nonexistent notification returns False."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = self._make_storage(tmp)
            assert not storage.delete("nonexistent")

    def test_count(self):
        """Count returns the number of stored notifications."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = self._make_storage(tmp)
            assert storage.count() == 0
            storage.create(Notification(message="One"))
            assert storage.count() == 1
            storage.create(Notification(message="Two"))
            assert storage.count() == 2

    def test_persistence(self):
        """Notifications survive a storage reload."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "notifications.json")
            storage1 = NotificationStorage(storage_file=path)
            storage1.create(Notification(message="Persistent"))

            storage2 = NotificationStorage(storage_file=path)
            assert storage2.count() == 1
            assert storage2.list_all()[0].message == "Persistent"

    def test_duplicate_id_raises(self):
        """Creating a notification with a duplicate ID raises ValueError."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = self._make_storage(tmp)
            n = Notification(id="dup-id", message="First")
            storage.create(n)
            with pytest.raises(ValueError, match="already exists"):
                storage.create(Notification(id="dup-id", message="Second"))


# =============================================================================
# Service Tests
# =============================================================================


class TestNotificationService:
    """Tests for NotificationService."""

    def _make_service(self, tmp_dir: str) -> NotificationService:
        path = os.path.join(tmp_dir, "notifications.json")
        storage = NotificationStorage(storage_file=path)
        return NotificationService(storage=storage)

    def test_create_notification(self):
        """Create a notification via the service."""
        with tempfile.TemporaryDirectory() as tmp:
            service = self._make_service(tmp)
            data = NotificationCreate(message="Hello!")
            n = service.create_notification(data)
            assert n.status == "queued"
            assert n.message == "Hello!"

    def test_list_notifications(self):
        """List all notifications."""
        with tempfile.TemporaryDirectory() as tmp:
            service = self._make_service(tmp)
            service.create_notification(NotificationCreate(message="One"))
            service.create_notification(NotificationCreate(message="Two"))
            assert len(service.list_notifications()) == 2

    def test_get_queued(self):
        """Get queued notifications ordered by priority."""
        with tempfile.TemporaryDirectory() as tmp:
            service = self._make_service(tmp)
            service.create_notification(NotificationCreate(message="Low", priority=1))
            service.create_notification(NotificationCreate(message="High", priority=5))
            service.create_notification(NotificationCreate(message="Medium", priority=3))

            queued = service.get_queued()
            assert len(queued) == 3
            assert queued[0].message == "High"
            assert queued[1].message == "Medium"
            assert queued[2].message == "Low"

    def test_mark_displayed(self):
        """Mark a notification as displayed."""
        with tempfile.TemporaryDirectory() as tmp:
            service = self._make_service(tmp)
            n = service.create_notification(NotificationCreate(message="Show me"))
            result = service.mark_displayed(n.id)
            assert result is not None
            assert result.status == "displayed"
            assert result.displayed_at is not None

    def test_mark_expired(self):
        """Mark a notification as expired."""
        with tempfile.TemporaryDirectory() as tmp:
            service = self._make_service(tmp)
            n = service.create_notification(NotificationCreate(message="Expire me"))
            service.mark_displayed(n.id)
            result = service.mark_expired(n.id)
            assert result is not None
            assert result.status == "expired"
            assert result.expired_at is not None

    def test_get_history(self):
        """Get displayed and expired notifications."""
        with tempfile.TemporaryDirectory() as tmp:
            service = self._make_service(tmp)
            n1 = service.create_notification(NotificationCreate(message="Displayed"))
            n2 = service.create_notification(NotificationCreate(message="Expired"))
            service.create_notification(NotificationCreate(message="Queued"))

            service.mark_displayed(n1.id)
            service.mark_displayed(n2.id)
            service.mark_expired(n2.id)

            history = service.get_history()
            assert len(history) == 2
            messages = [h.message for h in history]
            assert "Displayed" in messages
            assert "Expired" in messages
            assert "Queued" not in messages

    def test_expire_overdue(self):
        """Expire notifications that have exceeded their duration."""
        with tempfile.TemporaryDirectory() as tmp:
            service = self._make_service(tmp)
            n = service.create_notification(
                NotificationCreate(message="Short", duration_seconds=5)
            )
            # Mark displayed with a past timestamp
            service.storage.update(n.id, {
                "status": "displayed",
                "displayed_at": datetime.now(timezone.utc) - timedelta(seconds=60),
            })

            expired_ids = service.expire_overdue()
            assert n.id in expired_ids
            updated = service.get_notification(n.id)
            assert updated.status == "expired"

    def test_next_notification_returns_highest_priority(self):
        """next_notification returns the highest priority queued notification."""
        with tempfile.TemporaryDirectory() as tmp:
            service = self._make_service(tmp)
            service.create_notification(NotificationCreate(message="Low", priority=1))
            service.create_notification(NotificationCreate(message="High", priority=5))

            nxt = service.next_notification()
            assert nxt is not None
            assert nxt.message == "High"

    def test_next_notification_none_when_displayed(self):
        """next_notification returns None when something is currently displayed."""
        with tempfile.TemporaryDirectory() as tmp:
            service = self._make_service(tmp)
            n = service.create_notification(
                NotificationCreate(message="Displaying", duration_seconds=300)
            )
            service.mark_displayed(n.id)
            service.create_notification(NotificationCreate(message="Waiting"))

            assert service.next_notification() is None

    def test_next_notification_none_when_empty(self):
        """next_notification returns None when queue is empty."""
        with tempfile.TemporaryDirectory() as tmp:
            service = self._make_service(tmp)
            assert service.next_notification() is None

    def test_delete_notification(self):
        """Delete a notification via the service."""
        with tempfile.TemporaryDirectory() as tmp:
            service = self._make_service(tmp)
            n = service.create_notification(NotificationCreate(message="Delete me"))
            assert service.delete_notification(n.id)
            assert service.get_notification(n.id) is None
