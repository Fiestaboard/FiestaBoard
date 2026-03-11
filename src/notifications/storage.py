"""JSON file-based storage for notifications."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone

from .models import Notification

logger = logging.getLogger(__name__)


class NotificationStorage:
    """JSON file-based storage for notifications."""

    def __init__(self, storage_file: Optional[str] = None):
        if storage_file is None:
            project_root = Path(__file__).parent.parent.parent
            data_dir = project_root / "data"
            data_dir.mkdir(exist_ok=True)
            self.storage_file = data_dir / "notifications.json"
        else:
            self.storage_file = Path(storage_file)

        self._notifications: Dict[str, Notification] = {}
        self._load()

        logger.info(
            f"NotificationStorage initialized "
            f"(file: {self.storage_file}, notifications: {len(self._notifications)})"
        )

    def _load(self) -> None:
        if not self.storage_file.exists():
            self._notifications = {}
            return
        try:
            with open(self.storage_file, "r") as f:
                data = json.load(f)

            self._notifications = {}
            for item in data.get("notifications", []):
                try:
                    for dt_field in ("created_at", "displayed_at", "expired_at"):
                        if dt_field in item and isinstance(item[dt_field], str):
                            item[dt_field] = datetime.fromisoformat(item[dt_field])
                    notification = Notification(**item)
                    self._notifications[notification.id] = notification
                except Exception as e:
                    logger.warning(f"Failed to load notification: {e}")

            logger.info(f"Loaded {len(self._notifications)} notifications from storage")
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load notifications file: {e}")
            self._notifications = {}

    def _save(self) -> None:
        try:
            data = {
                "notifications": [n.model_dump() for n in self._notifications.values()]
            }
            for item in data["notifications"]:
                for dt_field in ("created_at", "displayed_at", "expired_at"):
                    if item.get(dt_field):
                        item[dt_field] = item[dt_field].isoformat()

            with open(self.storage_file, "w") as f:
                json.dump(data, f, indent=2)

            logger.debug(f"Saved {len(self._notifications)} notifications to storage")
        except IOError as e:
            logger.error(f"Failed to save notifications file: {e}")
            raise

    def list_all(self) -> List[Notification]:
        notifications = list(self._notifications.values())
        notifications.sort(key=lambda n: n.created_at, reverse=True)
        return notifications

    def get(self, notification_id: str) -> Optional[Notification]:
        return self._notifications.get(notification_id)

    def create(self, notification: Notification) -> Notification:
        if notification.id in self._notifications:
            raise ValueError(f"Notification with ID {notification.id} already exists")

        errors = notification.validate_config()
        if errors:
            raise ValueError(f"Invalid notification configuration: {errors}")

        self._notifications[notification.id] = notification
        self._save()
        logger.info(f"Created notification: {notification.id}")
        return notification

    def update(self, notification_id: str, updates: dict) -> Optional[Notification]:
        if notification_id not in self._notifications:
            return None

        notification = self._notifications[notification_id]
        notification_dict = notification.model_dump()
        for key, value in updates.items():
            if value is not None and key in notification_dict:
                notification_dict[key] = value

        updated = Notification(**notification_dict)

        errors = updated.validate_config()
        if errors:
            raise ValueError(f"Invalid notification configuration: {errors}")

        self._notifications[notification_id] = updated
        self._save()
        logger.info(f"Updated notification: {notification_id}")
        return updated

    def delete(self, notification_id: str) -> bool:
        if notification_id not in self._notifications:
            return False
        del self._notifications[notification_id]
        self._save()
        logger.info(f"Deleted notification: {notification_id}")
        return True

    def count(self) -> int:
        return len(self._notifications)
