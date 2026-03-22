"""State publisher for MQTT: reads FiestaBoard state and publishes to broker."""

import json
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class StatePublisher:
    """Gathers current state from services and publishes only changed values."""

    def __init__(
        self,
        client: "MQTTClient",
        get_display_running: Optional[Callable[[], bool]] = None,
        get_current_message: Optional[Callable[[], str]] = None,
    ):
        self._client = client
        self._get_display_running = get_display_running or (lambda: False)
        self._get_current_message = get_current_message or (lambda: "—")
        self._cache: dict[str, str] = {}
        self._last_display_update: str = ""
        self._prev_silence_mode: Optional[bool] = None
        self._prev_schedule_enabled: Optional[bool] = None
        self._prev_display_running: Optional[bool] = None

    def gather_and_publish(self) -> None:
        """Read state from services and publish changed values."""
        state = self._gather_state()
        attributes = self._gather_attributes()
        for object_id, value in state.items():
            if self._cache.get(object_id) != value:
                self._client.publish_state(object_id, value)
                self._cache[object_id] = value
        # Publish JSON attributes for entities that support them
        for object_id, attrs in attributes.items():
            attrs_json = json.dumps(attrs)
            cache_key = f"__attrs__{object_id}"
            if self._cache.get(cache_key) != attrs_json:
                self._client.publish_attributes(object_id, attrs_json)
                self._cache[cache_key] = attrs_json

    def publish_event(self, object_id: str, event_type: str, attributes: Optional[dict] = None) -> None:
        """Publish an event entity payload (JSON with event_type key)."""
        payload: dict = {"event_type": event_type}
        if attributes:
            payload.update(attributes)
        self._client.publish_state(object_id, json.dumps(payload))

    def mark_display_updated(self) -> None:
        """Record that the display was just updated (used for last_display_update sensor)."""
        self._last_display_update = datetime.now(timezone.utc).isoformat()

    def _gather_state(self) -> dict[str, str]:
        """Build a dict of object_id -> state value."""
        out: dict[str, str] = {}
        try:
            from src.settings.service import get_settings_service
            from src.pages.service import get_page_service
            from src.config import Config
            import src as src_pkg

            settings = get_settings_service()
            page_service = get_page_service()

            # schedule_enabled
            schedule_enabled = settings.is_schedule_enabled()
            out["schedule_enabled"] = "ON" if schedule_enabled else "OFF"

            # display_service
            display_running = self._get_display_running()
            out["display_service"] = "ON" if display_running else "OFF"

            # active_page, current_page: page name
            active_id = settings.get_active_page_id()
            page_name = "—"
            if active_id:
                page = page_service.get_page(active_id)
                if page:
                    page_name = page.name
            out["active_page"] = page_name
            out["current_page"] = page_name

            # transition_style
            trans = settings.get_transition_settings()
            out["transition_style"] = trans.strategy or ""

            # service_status
            out["service_status"] = "ON" if display_running else "OFF"

            # current_message
            out["current_message"] = self._get_current_message()

            # silence_mode
            silence_active = Config.is_silence_mode_active()
            out["silence_mode"] = "ON" if silence_active else "OFF"

            # version
            out["version"] = getattr(src_pkg, "__version__", "1.0.0")

            # page_count
            pages = page_service.list_pages()
            out["page_count"] = str(len(pages))

            # refresh_interval
            out["refresh_interval"] = str(settings.get_polling_interval())

            # uptime (diagnostic)
            out["uptime"] = self._get_uptime()

            # board_api_mode (diagnostic)
            out["board_api_mode"] = self._get_board_api_mode()

            # active_plugins (diagnostic)
            out["active_plugins"] = self._get_active_plugin_count()

            # last_display_update (diagnostic)
            out["last_display_update"] = self._last_display_update or ""

            # output_target (diagnostic)
            out["output_target"] = self._get_output_target()

            # Detect and fire events for state transitions
            self._check_state_transitions(silence_active, schedule_enabled, display_running)

        except Exception as e:
            logger.debug("State gather error: %s", e)
        return out

    def _check_state_transitions(self, silence_active: bool, schedule_enabled: bool, display_running: bool) -> None:
        """Fire events when boolean state values transition."""
        now = datetime.now(timezone.utc).isoformat()

        if self._prev_silence_mode is not None and self._prev_silence_mode != silence_active:
            event_type = "silence_mode_changed"
            self.publish_event("settings_changed", event_type, {
                "active": silence_active,
                "timestamp": now,
            })
        self._prev_silence_mode = silence_active

        if self._prev_schedule_enabled is not None and self._prev_schedule_enabled != schedule_enabled:
            self.publish_event("settings_changed", "schedule_toggled", {
                "enabled": schedule_enabled,
                "timestamp": now,
            })
        self._prev_schedule_enabled = schedule_enabled

        if self._prev_display_running is not None and self._prev_display_running != display_running:
            self.publish_event("settings_changed", "service_toggled", {
                "running": display_running,
                "timestamp": now,
            })
        self._prev_display_running = display_running

    def _gather_attributes(self) -> dict[str, dict]:
        """Build a dict of object_id -> JSON-serializable attributes."""
        out: dict[str, dict] = {}
        try:
            from src.settings.service import get_settings_service
            from src.pages.service import get_page_service

            settings = get_settings_service()
            page_service = get_page_service()

            # current_page attributes: page_id and page_index
            active_id = settings.get_active_page_id()
            pages = page_service.list_pages()
            page_attrs: dict = {"page_id": active_id or ""}
            for idx, page in enumerate(pages):
                if page.id == active_id:
                    page_attrs["page_index"] = idx
                    break
            out["current_page"] = page_attrs

        except Exception as e:
            logger.debug("Attributes gather error: %s", e)
        return out

    @staticmethod
    def _get_uptime() -> str:
        """Get service uptime in seconds as a string."""
        try:
            from src.api_server import _service_start_time
            import time
            if _service_start_time is not None:
                return str(int(time.time() - _service_start_time))
        except Exception:
            pass
        return "0"

    @staticmethod
    def _get_board_api_mode() -> str:
        """Get the board API mode (Local API or Cloud API)."""
        try:
            from src.api_server import _get_board_client
            client = _get_board_client()
            if client and hasattr(client, "use_cloud"):
                return "Cloud API" if client.use_cloud else "Local API"
        except Exception:
            pass
        return "Unknown"

    @staticmethod
    def _get_active_plugin_count() -> str:
        """Get the count of active (enabled) plugins."""
        try:
            from src.config_manager import ConfigManager
            cm = ConfigManager()
            plugins = cm._config.get("plugins", {})
            count = sum(
                1 for p in plugins.values()
                if isinstance(p, dict) and p.get("enabled", False)
            )
            return str(count)
        except Exception:
            pass
        return "0"

    @staticmethod
    def _get_output_target() -> str:
        """Get the current output target setting (ui, board, or both)."""
        try:
            from src.settings.service import get_settings_service
            output = get_settings_service().get_output_settings()
            return output.target or "both"
        except Exception:
            pass
        return "both"


# Type hint
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .client import MQTTClient
