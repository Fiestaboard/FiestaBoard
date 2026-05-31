"""Trigger service — manages event-based plugin triggers.

Plugins that set ``supports_triggers: true`` in their manifest can
implement ``check_triggers()`` to return :class:`TriggerResult` objects.
The :class:`TriggerService` periodically evaluates these, maintains a
set of *active* triggers, and exposes the highest-priority one so the
display loop can override the normal schedule/manual page.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..plugins.base import PluginBase, TriggerResult

logger = logging.getLogger(__name__)


@dataclass
class ActiveTrigger:
    """A trigger that has fired and is currently active.

    Attributes:
        trigger_id: Stable identifier (used for dedup / dismiss).
        plugin_id: Which plugin produced this trigger.
        message: Simple text message (may be None if formatted_lines set).
        formatted_lines: Pre-formatted board lines (may be None).
        data: Raw data dict for template rendering.
        priority: Higher = more important.
        duration_seconds: How long to keep showing the trigger.
        activated_at: When the trigger was activated.
    """
    trigger_id: str
    plugin_id: str
    message: str | None
    formatted_lines: list[str] | None
    data: dict[str, Any] | None
    priority: int
    duration_seconds: int
    activated_at: datetime = field(default_factory=datetime.now)

    def is_expired(self) -> bool:
        """Return True when the trigger has exceeded its duration."""
        age = (datetime.now() - self.activated_at).total_seconds()
        return age >= self.duration_seconds

    def remaining_seconds(self) -> float:
        """Return the number of seconds left before expiry."""
        age = (datetime.now() - self.activated_at).total_seconds()
        return max(0.0, self.duration_seconds - age)

    def to_dict(self) -> dict[str, Any]:
        """Serialise for API responses."""
        return {
            "trigger_id": self.trigger_id,
            "plugin_id": self.plugin_id,
            "message": self.message,
            "formatted_lines": self.formatted_lines,
            "data": self.data,
            "priority": self.priority,
            "duration_seconds": self.duration_seconds,
            "activated_at": self.activated_at.isoformat(),
            "remaining_seconds": round(self.remaining_seconds(), 1),
        }


class TriggerService:
    """Manages the lifecycle of plugin-originated triggers.

    * ``activate_trigger`` — record a fired trigger.
    * ``get_active_trigger`` — return the highest-priority non-expired
      trigger (or ``None``).
    * ``dismiss_trigger`` — manually dismiss a trigger by id.
    * ``clear_expired`` — remove triggers past their duration.
    * ``check_plugin_triggers`` — evaluate a single plugin and activate
      any fired triggers.
    """

    def __init__(self) -> None:
        self._active_triggers: dict[str, ActiveTrigger] = {}
        logger.info("TriggerService initialized")

    # -- public API --------------------------------------------------------

    def activate_trigger(self, plugin_id: str, trigger: TriggerResult) -> None:
        """Record a fired trigger (replaces any existing trigger with same id)."""
        active = ActiveTrigger(
            trigger_id=trigger.trigger_id,
            plugin_id=plugin_id,
            message=trigger.message,
            formatted_lines=trigger.formatted_lines,
            data=trigger.data,
            priority=trigger.priority,
            duration_seconds=trigger.duration_seconds,
            activated_at=datetime.now(),
        )
        self._active_triggers[trigger.trigger_id] = active
        logger.info(
            "Trigger activated: %s (plugin=%s, priority=%d, duration=%ds)",
            trigger.trigger_id,
            plugin_id,
            trigger.priority,
            trigger.duration_seconds,
        )

    def get_active_trigger(self) -> ActiveTrigger | None:
        """Return the highest-priority non-expired trigger, or None.

        Automatically clears expired triggers before selecting.
        """
        self.clear_expired()
        if not self._active_triggers:
            return None
        return max(self._active_triggers.values(), key=lambda t: t.priority)

    def list_active_triggers(self) -> list[ActiveTrigger]:
        """Return all active (non-expired) triggers sorted by priority desc."""
        self.clear_expired()
        return sorted(
            self._active_triggers.values(),
            key=lambda t: t.priority,
            reverse=True,
        )

    def dismiss_trigger(self, trigger_id: str) -> bool:
        """Dismiss (remove) a trigger by its id.

        Returns True if the trigger existed and was removed.
        """
        if trigger_id in self._active_triggers:
            del self._active_triggers[trigger_id]
            logger.info("Trigger dismissed: %s", trigger_id)
            return True
        return False

    def clear_expired(self) -> None:
        """Remove all triggers that have exceeded their duration."""
        expired = [
            tid for tid, t in self._active_triggers.items() if t.is_expired()
        ]
        for tid in expired:
            del self._active_triggers[tid]
            logger.debug("Trigger expired and removed: %s", tid)

    def clear_all(self) -> None:
        """Remove all active triggers."""
        self._active_triggers.clear()
        logger.info("All triggers cleared")

    def check_plugin_triggers(self, plugin: PluginBase) -> None:
        """Evaluate a plugin's triggers and activate any that fired.

        Skips disabled plugins and plugins that don't support triggers.
        Errors in ``check_triggers()`` are caught and logged.
        """
        if not plugin.enabled:
            return
        if not plugin.supports_triggers:
            return

        try:
            results = plugin.check_triggers()
        except Exception:
            logger.exception(
                "Error checking triggers for plugin %s", plugin.plugin_id
            )
            return

        for result in results:
            if result.triggered:
                self.activate_trigger(plugin.plugin_id, result)


# -- Singleton access ------------------------------------------------------

_trigger_service: TriggerService | None = None


def get_trigger_service() -> TriggerService:
    """Get or create the global trigger-service singleton."""
    global _trigger_service
    if _trigger_service is None:
        _trigger_service = TriggerService()
    return _trigger_service


def reset_trigger_service() -> None:
    """Reset the singleton (useful in tests or config reloads)."""
    global _trigger_service
    _trigger_service = None
    logger.info("TriggerService singleton reset")
