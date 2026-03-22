"""State publisher for MQTT: reads FiestaBoard state and publishes to broker."""

import json
import logging
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
            out["schedule_enabled"] = "ON" if settings.is_schedule_enabled() else "OFF"

            # display_service
            out["display_service"] = "ON" if self._get_display_running() else "OFF"

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
            out["service_status"] = "ON" if self._get_display_running() else "OFF"

            # current_message
            out["current_message"] = self._get_current_message()

            # silence_mode
            out["silence_mode"] = "ON" if Config.is_silence_mode_active() else "OFF"

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

        except Exception as e:
            logger.debug("State gather error: %s", e)
        return out

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


# Type hint
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .client import MQTTClient
