"""Command handler: dispatch MQTT commands to FiestaBoard services."""

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class CommandHandler:
    """Handles inbound MQTT commands from Home Assistant."""

    def __init__(
        self,
        client: "MQTTClient",
        start_display_service: Optional[Callable[[], bool]] = None,
        stop_display_service: Optional[Callable[[], bool]] = None,
    ):
        self._client = client
        self._start_display_service = start_display_service or (lambda: False)
        self._stop_display_service = stop_display_service or (lambda: False)

    def handle(self, object_id: str, payload: str) -> None:
        """Dispatch a command to the appropriate handler."""
        payload = (payload or "").strip()
        try:
            if object_id == "schedule_enabled":
                self._handle_schedule_enabled(payload)
            elif object_id == "display_service":
                self._handle_display_service(payload)
            elif object_id == "active_page":
                self._handle_active_page(payload)
            elif object_id == "transition_style":
                self._handle_transition_style(payload)
            elif object_id == "refresh_display":
                self._handle_refresh_display()
            elif object_id == "blank_board":
                self._handle_blank_board()
            elif object_id == "send_message":
                self._handle_send_message(payload)
            elif object_id == "refresh_interval":
                self._handle_refresh_interval(payload)
            else:
                logger.debug("Unknown MQTT command object_id=%s", object_id)
        except Exception as e:
            logger.exception("MQTT command failed object_id=%s: %s", object_id, e)
        # Publish updated state after handling so HA reflects the change
        if self._client._state_publisher:
            try:
                self._client._state_publisher.gather_and_publish()
            except Exception as e:
                logger.debug("State publish after command: %s", e)

    def _handle_schedule_enabled(self, payload: str) -> None:
        from src.settings.service import get_settings_service
        enabled = payload.upper() in ("ON", "1", "TRUE", "YES")
        get_settings_service().set_schedule_enabled(enabled)

    def _handle_display_service(self, payload: str) -> None:
        if payload.upper() in ("ON", "1", "TRUE", "YES"):
            if not self._start_display_service():
                logger.warning("MQTT display_service ON: start failed")
        else:
            self._stop_display_service()

    def _handle_active_page(self, payload: str) -> None:
        if not payload:
            return
        from src.settings.service import get_settings_service
        from src.pages.service import get_page_service
        page_service = get_page_service()
        for page in page_service.list_pages():
            if page.name == payload:
                get_settings_service().set_active_page_id(page.id)
                return
        logger.warning("MQTT active_page: no page named %r", payload)

    def _handle_transition_style(self, payload: str) -> None:
        if not payload:
            return
        from src.settings.service import get_settings_service
        from src.settings.service import VALID_STRATEGIES
        if payload not in VALID_STRATEGIES:
            logger.warning("MQTT transition_style: invalid %r", payload)
            return
        get_settings_service().update_transition_settings(strategy=payload)

    def _handle_refresh_display(self) -> None:
        from src.api_server import get_service
        service = get_service()
        if service:
            # Main DisplayService uses check_and_send_active_page for refresh
            if hasattr(service, "fetch_and_display"):
                service.fetch_and_display()
            elif hasattr(service, "check_and_send_active_page"):
                service.check_and_send_active_page()

    def _handle_blank_board(self) -> None:
        from src.api_server import _get_board_client
        client = _get_board_client()
        if not client:
            logger.warning("MQTT blank_board: board not configured")
            return
        from src.settings.service import get_settings_service
        if not get_settings_service().should_send_to_board():
            return
        blank_array = [[0] * 22 for _ in range(6)]
        client.send_characters(blank_array, force=True)

    def _handle_send_message(self, payload: str) -> None:
        if not payload:
            return
        from src.config import Config
        if Config.is_silence_mode_active():
            logger.info("MQTT send_message blocked by silence mode")
            return
        from src.api_server import get_service
        from src.text_to_board import text_to_board_array
        service = get_service()
        if not service or not service.vb_client:
            logger.warning("MQTT send_message: service or board not ready")
            return
        from src.settings.service import get_settings_service
        settings = get_settings_service()
        transition = settings.get_transition_settings()
        board_array = text_to_board_array(payload)
        service.vb_client.send_characters(
            board_array,
            strategy=transition.strategy,
            step_interval_ms=transition.step_interval_ms,
            step_size=transition.step_size,
        )

    def _handle_refresh_interval(self, payload: str) -> None:
        try:
            interval = int(payload)
        except ValueError:
            logger.warning("MQTT refresh_interval: invalid number %r", payload)
            return
        if interval < 10:
            interval = 10
        from src.settings.service import get_settings_service
        get_settings_service().set_polling_interval(interval)


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .client import MQTTClient
