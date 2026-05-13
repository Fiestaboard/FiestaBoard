"""Main application entry point for FiestaBoard Display Service."""

import logging
import time
import signal
from typing import Optional

import schedule

from .config import Config
from .board_client import BoardClient, board_client_from_board_dict
from .board_chars import BoardChars
from .devices import get_dimensions
from .text_to_board import text_to_board_array
from .settings.service import get_settings_service
from .pages.service import get_page_service
from .schedules.service import get_schedule_service
from .carousels.service import get_carousel_service
from .carousels.models import is_carousel_id
from .triggers.service import get_trigger_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


class DisplayService:
    """Main service for displaying information on the board."""
    
    def __init__(self):
        """Initialize the display service."""
        self.running = True
        self.vb_client: Optional[BoardClient] = None
        
        # Active page polling state
        self._last_active_page_content: Optional[str] = None
        self._last_active_page_id: Optional[str] = None
        self._last_silence_mode_active: bool = False
        self._snoozing_message_sent: bool = False
    
    def _build_board_clients(self):
        """Build board clients from settings.boards (first with connection) or Config. Sets self.vb_client."""
        settings_service = get_settings_service()
        boards = settings_service.get_board_settings().boards or []
        if boards:
            first = boards[0]
            if first.get("local_api_key") or first.get("cloud_key"):
                client = board_client_from_board_dict(first)
                if client:
                    self.vb_client = client
                    try:
                        self.vb_client.read_current_message(sync_cache=True)
                    except Exception as e:
                        logger.warning(f"Could not sync cache with board: {e}")
                    return
        use_cloud = Config.BOARD_API_MODE.lower() == "cloud"
        self.vb_client = BoardClient(
            api_key=Config.get_board_api_key(),
            host=Config.BOARD_HOST if not use_cloud else None,
            use_cloud=use_cloud,
            skip_unchanged=True,
        )
        try:
            self.vb_client.read_current_message(sync_cache=True)
        except Exception as e:
            logger.warning(f"Could not sync cache with board: {e}")

    def reinitialize_board_client(self) -> bool:
        """Reinitialize the board client with current config.

        Prefers first board from settings.boards when it has connection; else uses Config.
        """
        logger.info("Reinitializing board client with updated config...")
        try:
            self._build_board_clients()
            if self.vb_client:
                logger.info("Board client reinitialized successfully")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to reinitialize board client: {e}")
            return False
    
    def initialize(self) -> bool:
        """Initialize all components."""
        logger.info("Initializing FiestaBoard Display Service...")
        
        # Validate configuration
        if not Config.validate():
            logger.error("Configuration validation failed")
            return False
        
        # Initialize board client from settings.boards (first board) or Config
        try:
            self._build_board_clients()
            if not self.vb_client:
                logger.error("No board connection configured (settings.boards or config)")
                return False
            logger.info("Syncing cache with current board state...")
            # Log transition settings if configured
            transition = Config.get_transition_settings()
            if transition["strategy"]:
                logger.info(f"Default transition: {transition['strategy']} (interval={transition['step_interval_ms']}ms, step_size={transition['step_size']})")
        except Exception as e:
            logger.error(f"Failed to initialize board client: {e}")
            return False
        
        # Log configuration summary
        summary = Config.get_summary()
        logger.info(f"Configuration: {summary}")
        
        return True
    
    @staticmethod
    def _get_first_board_id() -> Optional[str]:
        """Return the ID of the first configured board, or None."""
        boards = get_settings_service().get_board_settings().boards or []
        if boards and isinstance(boards[0], dict):
            return boards[0].get("id")
        return None

    def check_and_send_active_page(self) -> bool:
        """Check the active page and send to board if content changed.
        
        Respects schedule mode - uses schedule-based page selection when enabled,
        otherwise falls back to manual active page setting.
        Active triggers take priority over scheduled/manual pages.
            
        Returns:
            True if content was sent to board, False otherwise
        """
        try:
            settings_service = get_settings_service()
            page_service = get_page_service()
            schedule_service = get_schedule_service()

            # --- Silence mode short-circuit (evaluated FIRST) ---
            # Important: we evaluate silence before doing ANY plugin/API work
            # (trigger evaluation, page rendering, carousel resolution) so a
            # "snoozed" board doesn't cause weather/transit/stocks/etc. APIs
            # to be hit on every poll. We send exactly one update when entering
            # silence (with the SNOOZING indicator) and then go quiet until
            # the silence window ends.
            silence_mode_active = Config.is_silence_mode_active()
            entering_silence_mode = silence_mode_active and not self._last_silence_mode_active
            exiting_silence_mode = not silence_mode_active and self._last_silence_mode_active

            if silence_mode_active and self._snoozing_message_sent:
                # Steady-state silence: indicator is already on the board.
                # Do nothing — no rendering, no plugin fetches, no trigger
                # evaluation, no board send.
                # (If we are here, _snoozing_message_sent=True implies a prior
                # successful silence-mode send, which set _last_silence_mode_active
                # to True, so this is necessarily not the entering-silence tick.)
                logger.debug("Silence mode active - skipping update (board already snoozing)")
                self._last_silence_mode_active = True
                return False

            if exiting_silence_mode:
                logger.info("▶️  Exiting silence mode - resuming normal updates")
                self._snoozing_message_sent = False
                # The board currently shows the SNOOZING indicator on top of
                # whatever content was last rendered. Clear the content cache
                # so the next render is unconditionally pushed to the board,
                # otherwise we'd see "content unchanged, skipping send" and
                # leave the indicator stuck on the board.
                self._last_active_page_content = None

            # --- Check for active triggers (highest priority, but suppressed during silence) ---
            if not silence_mode_active:
                trigger_content = self._check_trigger_override()
                if trigger_content is not None:
                    return self._send_trigger_content(trigger_content)

            # Determine active page based on schedule mode
            if settings_service.is_schedule_enabled():
                # Schedule mode: Use schedule service to determine page
                # Use TimeService to get current time in configured timezone
                from .time_service import get_time_service
                time_service = get_time_service()
                now = time_service.get_current_time()
                current_time = now.time()
                current_day = now.strftime("%A").lower()  # monday, tuesday, etc.
                
                # Pass the first board's ID so schedules scoped to that board are found
                board_id = self._get_first_board_id()
                active_page_id = schedule_service.get_active_page_id(current_time, current_day, board_id=board_id)
                
                if active_page_id:
                    logger.debug(f"Schedule mode: Active page determined by schedule: {active_page_id}")
                else:
                    logger.debug(f"Schedule mode: No matching schedule for {current_day} {current_time.strftime('%H:%M')}")
            else:
                # Manual mode: Use manual active page setting
                active_page_id = settings_service.get_active_page_id()
                logger.debug(f"Manual mode: Using manual active page: {active_page_id}")
            
            # No active page set - try to default to first page (manual mode only)
            if not active_page_id and not settings_service.is_schedule_enabled():
                pages = page_service.list_pages()
                if pages:
                    active_page_id = pages[0].id
                    settings_service.set_active_page_id(active_page_id)
                    logger.info(f"No active page set, defaulting to first page: {active_page_id}")
                else:
                    logger.debug("No active page and no pages available")
                    return False
            
            # If schedule mode but no page (gap without default), don't update board
            if not active_page_id:
                logger.debug("No active page available (schedule gap with no default)")
                return False

            # Resolve carousels: if the active ref is a carousel, determine
            # which underlying page should be shown right now.
            carousel_service = get_carousel_service()
            if is_carousel_id(active_page_id):
                resolved = carousel_service.resolve_page_id(active_page_id)
                if not resolved:
                    logger.warning(f"Carousel not found or empty: {active_page_id}")
                    return False
                logger.debug(f"Carousel {active_page_id} resolved to page {resolved}")
                active_page_id = resolved

            # Get the page for transition settings
            page = page_service.get_page(active_page_id)
            if not page:
                logger.warning(f"Active page not found: {active_page_id}")
                return False
            
            # Render the page with fresh data — force_refresh bypasses the preview
            # cache so template variables (weather, time, stocks, etc.) are current.
            result = page_service.preview_page(active_page_id, force_refresh=True)
            if not result or not result.available:
                logger.warning(f"Failed to render active page: {active_page_id}")
                return False
            
            # Silence-mode state was already evaluated at the top of this method.
            # If we get here while silence is active, it means we are entering
            # silence (or recovering from a missing indicator after restart /
            # power outage) and need to send exactly one update with the
            # silence-mode display, or suppress updates entirely (freeze mode).
            if silence_mode_active:
                silence_mode = Config.SILENCE_SCHEDULE_MODE
                if silence_mode == "freeze":
                    if entering_silence_mode:
                        logger.info("⏸️  Entering silence mode (freeze) - leaving board untouched")
                    else:
                        logger.debug("Silence mode active (freeze) - blocking update")
                    self._last_silence_mode_active = True
                    self._snoozing_message_sent = True
                    return False
                if silence_mode == "page":
                    return self._send_silence_page()
                return self._send_silence_indicator(page.device_type)

            # Get base content
            current_content = result.formatted
            content_to_send = current_content

            # Normal mode (not in silence) - check if content changed
            if (current_content == self._last_active_page_content and
                    active_page_id == self._last_active_page_id):
                logger.debug("Active page content unchanged, skipping send")
                return False
            logger.info(f"Active page content changed, sending to board: {active_page_id}")
            
            # At this point, we're going to send an update
            
            if not self.vb_client:
                logger.warning("Board client not initialized")
                return False
            
            # Get transition settings - use page-level if set, otherwise system defaults
            system_transition = settings_service.get_transition_settings()
            strategy = page.transition_strategy if page.transition_strategy else system_transition.strategy
            interval_ms = page.transition_interval_ms if page.transition_interval_ms is not None else system_transition.step_interval_ms
            step_size = page.transition_step_size if page.transition_step_size is not None else system_transition.step_size
            
            # Send to board
            dims = get_dimensions(page.device_type)
            board_array = text_to_board_array(content_to_send, rows=dims.rows, cols=dims.cols)

            success, was_sent = self.vb_client.send_characters(
                board_array,
                strategy=strategy,
                step_interval_ms=interval_ms,
                step_size=step_size
            )

            if success:
                self._last_active_page_content = content_to_send
                self._last_active_page_id = active_page_id
                self._last_silence_mode_active = silence_mode_active


                if was_sent:
                    logger.info(f"Active page sent to board: {active_page_id}")
                else:
                    logger.debug("Active page unchanged at board level")
                return was_sent
            else:
                logger.error(f"Failed to send active page to board: {active_page_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error checking active page: {e}")
            return False

    # ------------------------------------------------------------------ #
    # Silence-mode helpers
    # ------------------------------------------------------------------ #

    def _silence_device_type(self) -> str:
        """Pick a device type for the silence display.

        Prefers the first configured board's device type so the silence
        display is sized for the actual hardware (Note vs Flagship). Falls
        back to flagship.
        """
        try:
            boards = get_settings_service().get_board_settings().boards or []
            if boards and isinstance(boards[0], dict):
                device_type = boards[0].get("device_type")
                if device_type in ("flagship", "note"):
                    return device_type
        except Exception as e:
            logger.warning("Could not determine device type from board settings: %s", e)
        return "flagship"

    def _build_silence_indicator_array(self, device_type: str):
        """Build a clean board array with 'SNOOZING' centered.

        Sized for the given device so the message fits the Note (15 cols)
        as well as the Flagship (22 cols) without overlaying other content.
        """
        dims = get_dimensions(device_type)
        board_array = [[BoardChars.SPACE] * dims.cols for _ in range(dims.rows)]

        indicator = Config.SILENCE_SCHEDULE_INDICATOR_TEXT
        # Truncate to fit if a future device is narrower.
        text = indicator[: dims.cols]

        position = Config.SILENCE_SCHEDULE_INDICATOR_POSITION
        if position == "top-left":
            row, start_col = 0, 0
        elif position == "top-right":
            row, start_col = 0, max(0, dims.cols - len(text))
        elif position == "bottom-left":
            row, start_col = dims.rows - 1, 0
        elif position == "bottom-right":
            row, start_col = dims.rows - 1, max(0, dims.cols - len(text))
        else:  # center (default)
            row = dims.rows // 2
            start_col = max(0, (dims.cols - len(text)) // 2)
        for i, char in enumerate(text):
            char_code = BoardChars.get_char_code(char)
            if char_code is not None:
                board_array[row][start_col + i] = char_code
        return board_array

    def _send_silence_indicator(self, page_device_type: str) -> bool:
        """Send a clean SNOOZING-only board sized for the device."""
        if not self.vb_client:
            logger.warning("Board client not initialized")
            return False

        device_type = self._silence_device_type() or page_device_type
        logger.info(f"⏸️  Entering silence mode (indicator) - displaying SNOOZING for {device_type}")

        settings_service = get_settings_service()
        system_transition = settings_service.get_transition_settings()
        board_array = self._build_silence_indicator_array(device_type)

        success, was_sent = self.vb_client.send_characters(
            board_array,
            strategy=system_transition.strategy,
            step_interval_ms=system_transition.step_interval_ms,
            step_size=system_transition.step_size,
        )

        if success:
            self._last_active_page_content = "snoozing"
            self._last_active_page_id = "__silence__"
            self._last_silence_mode_active = True
            self._snoozing_message_sent = True
            logger.info("🔇 Silence mode active - further updates blocked until silence ends")
            return was_sent

        logger.error("Failed to send silence indicator to board")
        return False

    def _send_silence_page(self) -> bool:
        """Render the configured silence page once and freeze it on the board.

        Variables in the page are rendered with the values present at the
        moment silence begins; the board is not refreshed afterwards.
        """
        if not self.vb_client:
            logger.warning("Board client not initialized")
            return False

        page_id = Config.SILENCE_SCHEDULE_PAGE_ID
        page_service = get_page_service()
        page = page_service.get_page(page_id) if page_id else None

        if not page:
            logger.warning(
                "Silence mode 'page' selected but page %r not found - falling back to indicator",
                page_id,
            )
            return self._send_silence_indicator(self._silence_device_type())

        logger.info(f"⏸️  Entering silence mode (page) - displaying {page.id}")

        result = page_service.preview_page(page.id, force_refresh=True)
        if not result or not result.available:
            logger.warning(
                "Silence page %s could not be rendered - falling back to indicator", page.id
            )
            return self._send_silence_indicator(page.device_type)

        settings_service = get_settings_service()
        system_transition = settings_service.get_transition_settings()
        strategy = page.transition_strategy or system_transition.strategy
        interval_ms = (
            page.transition_interval_ms
            if page.transition_interval_ms is not None
            else system_transition.step_interval_ms
        )
        step_size = (
            page.transition_step_size
            if page.transition_step_size is not None
            else system_transition.step_size
        )

        dims = get_dimensions(page.device_type)
        board_array = text_to_board_array(result.formatted, rows=dims.rows, cols=dims.cols)

        success, was_sent = self.vb_client.send_characters(
            board_array,
            strategy=strategy,
            step_interval_ms=interval_ms,
            step_size=step_size,
        )

        if success:
            self._last_active_page_content = result.formatted
            self._last_active_page_id = f"__silence_page__:{page.id}"
            self._last_silence_mode_active = True
            self._snoozing_message_sent = True
            logger.info("🔇 Silence page sent - further updates blocked until silence ends")
            return was_sent

        logger.error("Failed to send silence page to board")
        return False

    def _check_trigger_override(self) -> Optional[str]:
        """Check all trigger-capable plugins and return content if a trigger is active.

        Returns:
            Formatted text content from the highest-priority active trigger,
            or None if no triggers are active.
        """
        try:
            from .plugins.registry import get_plugin_registry
            registry = get_plugin_registry()
            trigger_service = get_trigger_service()

            # Evaluate triggers for all enabled trigger-capable plugins
            for plugin_id, plugin in registry.trigger_plugins.items():
                trigger_service.check_plugin_triggers(plugin)

            active = trigger_service.get_active_trigger()
            if active is None:
                return None

            # Build display content from the trigger
            if active.formatted_lines:
                return "\n".join(active.formatted_lines)
            if active.message:
                return active.message
            return None
        except Exception as e:
            logger.error(f"Error checking triggers: {e}")
            return None

    def _send_trigger_content(self, content: str) -> bool:
        """Send trigger content to the board.

        Returns True if the content was sent successfully.
        """
        if not self.vb_client:
            logger.warning("Board client not initialized")
            return False

        if content == self._last_active_page_content:
            logger.debug("Trigger content unchanged, skipping send")
            return False

        logger.info("Sending triggered message to board")
        settings_service = get_settings_service()
        system_transition = settings_service.get_transition_settings()

        dims = get_dimensions(self._silence_device_type())
        board_array = text_to_board_array(content, rows=dims.rows, cols=dims.cols)

        success, was_sent = self.vb_client.send_characters(
            board_array,
            strategy=system_transition.strategy,
            step_interval_ms=system_transition.step_interval_ms,
            step_size=system_transition.step_size,
        )

        if success:
            self._last_active_page_content = content
            self._last_active_page_id = "__trigger__"
            if was_sent:
                logger.info("Triggered message sent to board")
            return was_sent
        else:
            logger.error("Failed to send triggered message to board")
            return False

    def _get_active_ref_id(self) -> Optional[str]:
        """Return the raw active-page/carousel reference (before carousel resolution)."""
        settings_service = get_settings_service()
        if settings_service.is_schedule_enabled():
            from .time_service import get_time_service
            ts = get_time_service()
            now = ts.get_current_time()
            # Pass the first board's ID so schedules scoped to that board are found
            board_id = self._get_first_board_id()
            return get_schedule_service().get_active_page_id(now.time(), now.strftime("%A").lower(), board_id=board_id)
        return settings_service.get_active_page_id()

    def run(self):
        """Run the main service loop."""
        self.running = True
        
        if not self.vb_client and not self.initialize():
            logger.error("Initialization failed")
            return
        
        schedule.clear()
        
        settings_service = get_settings_service()
        polling_interval = settings_service.get_polling_interval()
        
        schedule.every(polling_interval).seconds.do(self.check_and_send_active_page)
        logger.info(f"Active page polling scheduled every {polling_interval} seconds")
        
        logger.info("Sending initial active page...")
        self.check_and_send_active_page()
        
        logger.info("Service started, waiting for scheduled updates...")
        _next_carousel_check: float = time.time()
        try:
            while self.running:
                schedule.run_pending()
                # When a carousel is active, poll at the carousel's interval
                now = time.time()
                if now >= _next_carousel_check:
                    ref_id = self._get_active_ref_id()
                    if ref_id and is_carousel_id(ref_id):
                        carousel_service = get_carousel_service()
                        secs = carousel_service.seconds_until_next_page(ref_id, now)
                        if secs is not None:
                            self.check_and_send_active_page()
                            _next_carousel_check = now + max(1, secs)
                        else:
                            _next_carousel_check = now + polling_interval
                    else:
                        _next_carousel_check = now + polling_interval
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            logger.info("Service stopped")


def main():
    """Main entry point (standalone mode only, not used under uvicorn)."""
    service = DisplayService()
    signal.signal(signal.SIGINT, lambda s, f: _stop_service(service))
    signal.signal(signal.SIGTERM, lambda s, f: _stop_service(service))
    service.run()


def _stop_service(service):
    logger.info("Received shutdown signal, stopping gracefully...")
    service.running = False


# Aliases for the display service class
FiestaBoardDisplayService = DisplayService
# Backward compatibility alias
FiestaboardDisplayService = DisplayService


if __name__ == "__main__":
    main()
