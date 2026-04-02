"""Tests for plugin trigger system.

Tests the ability for plugins to trigger messages based on events,
rather than pre-scheduled time slots.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.plugins.base import (
    PluginBase,
    PluginResult,
    TriggerResult,
)


# -- Test fixtures: concrete plugins with/without trigger support ----------


MANIFEST_WITH_TRIGGERS = {
    "id": "trigger_plugin",
    "name": "Trigger Plugin",
    "version": "1.0.0",
    "supports_triggers": True,
    "settings_schema": {
        "type": "object",
        "properties": {
            "threshold": {
                "type": "integer",
                "default": 50,
            }
        },
    },
}

MANIFEST_WITHOUT_TRIGGERS = {
    "id": "normal_plugin",
    "name": "Normal Plugin",
    "version": "1.0.0",
}


class TriggerPlugin(PluginBase):
    """Plugin that supports triggers for testing."""

    def __init__(self, manifest, triggers=None):
        super().__init__(manifest)
        self._triggers = triggers or []

    @property
    def plugin_id(self) -> str:
        return "trigger_plugin"

    def fetch_data(self) -> PluginResult:
        return PluginResult(available=True, data={"value": 42})

    def check_triggers(self) -> List[TriggerResult]:
        return self._triggers


class NormalPlugin(PluginBase):
    """Plugin without trigger support for testing."""

    @property
    def plugin_id(self) -> str:
        return "normal_plugin"

    def fetch_data(self) -> PluginResult:
        return PluginResult(available=True, data={"value": 1})


class ErrorTriggerPlugin(PluginBase):
    """Plugin whose check_triggers raises an exception."""

    @property
    def plugin_id(self) -> str:
        return "error_trigger_plugin"

    def fetch_data(self) -> PluginResult:
        return PluginResult(available=True, data={})

    def check_triggers(self) -> List[TriggerResult]:
        raise RuntimeError("trigger check failed")


# -- TriggerResult dataclass tests ----------------------------------------


class TestTriggerResult:
    def test_default_values(self):
        result = TriggerResult(triggered=False)
        assert result.triggered is False
        assert result.trigger_id == ""
        assert result.message is None
        assert result.formatted_lines is None
        assert result.priority == 0
        assert result.duration_seconds == 30
        assert result.data is None

    def test_triggered_with_message(self):
        result = TriggerResult(
            triggered=True,
            trigger_id="air_quality_alert",
            message="AQI ABOVE 150",
            priority=5,
            duration_seconds=120,
        )
        assert result.triggered is True
        assert result.trigger_id == "air_quality_alert"
        assert result.message == "AQI ABOVE 150"
        assert result.priority == 5
        assert result.duration_seconds == 120

    def test_triggered_with_formatted_lines(self):
        lines = [
            "CUBS GAME",
            "CHC 5 - STL 3",
            "",
            "TOP 7TH",
            "",
            "",
        ]
        result = TriggerResult(
            triggered=True,
            trigger_id="game_score",
            formatted_lines=lines,
            priority=3,
            duration_seconds=60,
        )
        assert result.formatted_lines == lines
        assert len(result.formatted_lines) == 6

    def test_triggered_with_data(self):
        result = TriggerResult(
            triggered=True,
            trigger_id="score_update",
            data={"home_team": "Cubs", "away_team": "Cardinals", "score": "5-3"},
            duration_seconds=60,
        )
        assert result.data["home_team"] == "Cubs"
        assert result.data["score"] == "5-3"

    def test_to_dict(self):
        result = TriggerResult(
            triggered=True,
            trigger_id="test_trigger",
            message="Test Message",
            priority=2,
            duration_seconds=45,
            data={"key": "value"},
        )
        d = result.to_dict()
        assert d["triggered"] is True
        assert d["trigger_id"] == "test_trigger"
        assert d["message"] == "Test Message"
        assert d["priority"] == 2
        assert d["duration_seconds"] == 45
        assert d["data"] == {"key": "value"}

    def test_to_dict_minimal(self):
        result = TriggerResult(triggered=False)
        d = result.to_dict()
        assert d["triggered"] is False
        assert d["trigger_id"] == ""
        assert d["message"] is None


# -- PluginBase trigger methods tests --------------------------------------


class TestPluginBaseTriggers:
    def test_default_check_triggers_returns_empty(self):
        """Plugins that don't override check_triggers return empty list."""
        plugin = NormalPlugin(MANIFEST_WITHOUT_TRIGGERS)
        assert plugin.check_triggers() == []

    def test_supports_triggers_from_manifest(self):
        plugin = TriggerPlugin(MANIFEST_WITH_TRIGGERS)
        assert plugin.supports_triggers is True

    def test_no_trigger_support_by_default(self):
        plugin = NormalPlugin(MANIFEST_WITHOUT_TRIGGERS)
        assert plugin.supports_triggers is False

    def test_check_triggers_returns_results(self):
        triggers = [
            TriggerResult(
                triggered=True,
                trigger_id="test_alert",
                message="ALERT!",
                priority=1,
            )
        ]
        plugin = TriggerPlugin(MANIFEST_WITH_TRIGGERS, triggers=triggers)
        results = plugin.check_triggers()
        assert len(results) == 1
        assert results[0].triggered is True
        assert results[0].trigger_id == "test_alert"

    def test_check_triggers_multiple_results(self):
        triggers = [
            TriggerResult(triggered=True, trigger_id="alert_1", message="A"),
            TriggerResult(triggered=False, trigger_id="alert_2", message="B"),
            TriggerResult(triggered=True, trigger_id="alert_3", message="C"),
        ]
        plugin = TriggerPlugin(MANIFEST_WITH_TRIGGERS, triggers=triggers)
        results = plugin.check_triggers()
        assert len(results) == 3
        fired = [r for r in results if r.triggered]
        assert len(fired) == 2

    def test_check_triggers_requires_enabled(self):
        """check_triggers works regardless of enabled state (caller filters)."""
        triggers = [TriggerResult(triggered=True, trigger_id="t1", message="X")]
        plugin = TriggerPlugin(MANIFEST_WITH_TRIGGERS, triggers=triggers)
        plugin.enabled = False
        results = plugin.check_triggers()
        assert len(results) == 1


# -- TriggerService tests -------------------------------------------------


class TestTriggerService:
    """Tests for the TriggerService that manages trigger lifecycle."""

    @pytest.fixture
    def trigger_service(self):
        from src.triggers.service import TriggerService
        return TriggerService()

    def test_no_active_triggers_initially(self, trigger_service):
        assert trigger_service.get_active_trigger() is None

    def test_activate_trigger(self, trigger_service):
        trigger = TriggerResult(
            triggered=True,
            trigger_id="test_1",
            message="ALERT",
            priority=1,
            duration_seconds=60,
        )
        trigger_service.activate_trigger("my_plugin", trigger)
        active = trigger_service.get_active_trigger()
        assert active is not None
        assert active.trigger_id == "test_1"
        assert active.plugin_id == "my_plugin"
        assert active.message == "ALERT"

    def test_highest_priority_wins(self, trigger_service):
        low = TriggerResult(
            triggered=True,
            trigger_id="low_prio",
            message="Low Priority",
            priority=1,
            duration_seconds=60,
        )
        high = TriggerResult(
            triggered=True,
            trigger_id="high_prio",
            message="High Priority",
            priority=10,
            duration_seconds=60,
        )
        trigger_service.activate_trigger("plugin_a", low)
        trigger_service.activate_trigger("plugin_b", high)
        active = trigger_service.get_active_trigger()
        assert active.trigger_id == "high_prio"
        assert active.priority == 10

    def test_dismiss_trigger(self, trigger_service):
        trigger = TriggerResult(
            triggered=True,
            trigger_id="dismiss_me",
            message="X",
            priority=1,
            duration_seconds=60,
        )
        trigger_service.activate_trigger("plugin_a", trigger)
        assert trigger_service.get_active_trigger() is not None

        result = trigger_service.dismiss_trigger("dismiss_me")
        assert result is True
        assert trigger_service.get_active_trigger() is None

    def test_dismiss_nonexistent_trigger(self, trigger_service):
        result = trigger_service.dismiss_trigger("does_not_exist")
        assert result is False

    def test_expired_triggers_cleared(self, trigger_service):
        trigger = TriggerResult(
            triggered=True,
            trigger_id="expires_soon",
            message="Short-lived",
            priority=1,
            duration_seconds=1,
        )
        trigger_service.activate_trigger("plugin_a", trigger)

        # Manually set activation time to the past
        trigger_service._active_triggers["expires_soon"].activated_at = (
            datetime.now() - timedelta(seconds=10)
        )

        trigger_service.clear_expired()
        assert trigger_service.get_active_trigger() is None

    def test_non_expired_trigger_stays(self, trigger_service):
        trigger = TriggerResult(
            triggered=True,
            trigger_id="stays",
            message="Long-lived",
            priority=1,
            duration_seconds=3600,
        )
        trigger_service.activate_trigger("plugin_a", trigger)
        trigger_service.clear_expired()
        assert trigger_service.get_active_trigger() is not None

    def test_list_active_triggers(self, trigger_service):
        t1 = TriggerResult(triggered=True, trigger_id="t1", message="A", priority=1, duration_seconds=60)
        t2 = TriggerResult(triggered=True, trigger_id="t2", message="B", priority=2, duration_seconds=60)
        trigger_service.activate_trigger("p1", t1)
        trigger_service.activate_trigger("p2", t2)

        active = trigger_service.list_active_triggers()
        assert len(active) == 2
        # Sorted by priority descending
        assert active[0].trigger_id == "t2"
        assert active[1].trigger_id == "t1"

    def test_duplicate_trigger_id_updates(self, trigger_service):
        """Activating a trigger with the same ID replaces the old one."""
        t1 = TriggerResult(triggered=True, trigger_id="same_id", message="Old", priority=1, duration_seconds=60)
        t2 = TriggerResult(triggered=True, trigger_id="same_id", message="New", priority=5, duration_seconds=120)
        trigger_service.activate_trigger("plugin_a", t1)
        trigger_service.activate_trigger("plugin_a", t2)

        active = trigger_service.list_active_triggers()
        assert len(active) == 1
        assert active[0].message == "New"
        assert active[0].priority == 5

    def test_clear_all(self, trigger_service):
        t1 = TriggerResult(triggered=True, trigger_id="t1", message="A", priority=1, duration_seconds=60)
        t2 = TriggerResult(triggered=True, trigger_id="t2", message="B", priority=2, duration_seconds=60)
        trigger_service.activate_trigger("p1", t1)
        trigger_service.activate_trigger("p2", t2)
        trigger_service.clear_all()
        assert trigger_service.list_active_triggers() == []

    def test_check_plugin_triggers(self, trigger_service):
        """check_plugin_triggers calls plugin.check_triggers and activates fired triggers."""
        triggers = [
            TriggerResult(triggered=True, trigger_id="fired", message="FIRE!", priority=3, duration_seconds=30),
            TriggerResult(triggered=False, trigger_id="not_fired"),
        ]
        plugin = TriggerPlugin(MANIFEST_WITH_TRIGGERS, triggers=triggers)
        plugin.enabled = True

        trigger_service.check_plugin_triggers(plugin)
        active = trigger_service.list_active_triggers()
        assert len(active) == 1
        assert active[0].trigger_id == "fired"

    def test_check_plugin_triggers_skips_disabled(self, trigger_service):
        """Disabled plugins are skipped."""
        triggers = [TriggerResult(triggered=True, trigger_id="t1", message="X")]
        plugin = TriggerPlugin(MANIFEST_WITH_TRIGGERS, triggers=triggers)
        plugin.enabled = False

        trigger_service.check_plugin_triggers(plugin)
        assert trigger_service.list_active_triggers() == []

    def test_check_plugin_triggers_skips_non_trigger_plugins(self, trigger_service):
        plugin = NormalPlugin(MANIFEST_WITHOUT_TRIGGERS)
        plugin.enabled = True

        trigger_service.check_plugin_triggers(plugin)
        assert trigger_service.list_active_triggers() == []

    def test_check_plugin_triggers_handles_errors_gracefully(self, trigger_service):
        """If check_triggers raises, the service logs and continues."""
        plugin = ErrorTriggerPlugin({
            "id": "error_trigger_plugin",
            "name": "Error Plugin",
            "version": "1.0.0",
            "supports_triggers": True,
        })
        plugin.enabled = True

        # Should not raise
        trigger_service.check_plugin_triggers(plugin)
        assert trigger_service.list_active_triggers() == []

    def test_get_active_trigger_returns_none_after_expiry(self, trigger_service):
        trigger = TriggerResult(
            triggered=True,
            trigger_id="temp",
            message="Temporary",
            priority=1,
            duration_seconds=1,
        )
        trigger_service.activate_trigger("p1", trigger)
        trigger_service._active_triggers["temp"].activated_at = (
            datetime.now() - timedelta(seconds=10)
        )
        # get_active_trigger should auto-clear expired
        assert trigger_service.get_active_trigger() is None


# -- ActiveTrigger model tests --------------------------------------------


class TestActiveTrigger:
    def test_is_expired(self):
        from src.triggers.service import ActiveTrigger
        trigger = ActiveTrigger(
            trigger_id="t1",
            plugin_id="p1",
            message="Test",
            formatted_lines=None,
            data=None,
            priority=1,
            duration_seconds=60,
            activated_at=datetime.now() - timedelta(seconds=120),
        )
        assert trigger.is_expired() is True

    def test_is_not_expired(self):
        from src.triggers.service import ActiveTrigger
        trigger = ActiveTrigger(
            trigger_id="t1",
            plugin_id="p1",
            message="Test",
            formatted_lines=None,
            data=None,
            priority=1,
            duration_seconds=3600,
            activated_at=datetime.now(),
        )
        assert trigger.is_expired() is False

    def test_remaining_seconds(self):
        from src.triggers.service import ActiveTrigger
        trigger = ActiveTrigger(
            trigger_id="t1",
            plugin_id="p1",
            message="Test",
            formatted_lines=None,
            data=None,
            priority=1,
            duration_seconds=60,
            activated_at=datetime.now() - timedelta(seconds=30),
        )
        remaining = trigger.remaining_seconds()
        assert 25 <= remaining <= 35  # ~30 seconds remaining

    def test_to_dict(self):
        from src.triggers.service import ActiveTrigger
        now = datetime.now()
        trigger = ActiveTrigger(
            trigger_id="t1",
            plugin_id="p1",
            message="Hello",
            formatted_lines=["LINE 1", "LINE 2"],
            data={"key": "val"},
            priority=5,
            duration_seconds=120,
            activated_at=now,
        )
        d = trigger.to_dict()
        assert d["trigger_id"] == "t1"
        assert d["plugin_id"] == "p1"
        assert d["message"] == "Hello"
        assert d["formatted_lines"] == ["LINE 1", "LINE 2"]
        assert d["data"] == {"key": "val"}
        assert d["priority"] == 5
        assert d["duration_seconds"] == 120
        assert "activated_at" in d
        assert "remaining_seconds" in d


# -- Singleton tests -------------------------------------------------------


class TestTriggerServiceSingleton:
    def test_get_trigger_service_returns_singleton(self):
        from src.triggers.service import get_trigger_service, reset_trigger_service
        reset_trigger_service()
        svc1 = get_trigger_service()
        svc2 = get_trigger_service()
        assert svc1 is svc2
        reset_trigger_service()

    def test_reset_trigger_service(self):
        from src.triggers.service import get_trigger_service, reset_trigger_service
        svc1 = get_trigger_service()
        reset_trigger_service()
        svc2 = get_trigger_service()
        assert svc1 is not svc2
        reset_trigger_service()
