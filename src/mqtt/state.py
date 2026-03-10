"""State publisher for MQTT: reads FiestaBoard state and publishes to broker."""

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
        for object_id, value in state.items():
            if self._cache.get(object_id) != value:
                self._client.publish_state(object_id, value)
                self._cache[object_id] = value

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

        except Exception as e:
            logger.debug("State gather error: %s", e)
        return out


# Type hint
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .client import MQTTClient
