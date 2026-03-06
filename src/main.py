"""Main application entry point for FiestaBoard Display Service."""

import logging
import time
import signal
from datetime import datetime
from typing import Optional

import schedule

from .config import Config
from .board_client import BoardClient, board_client_from_board_dict
from .board_chars import BoardChars
from .devices import get_dimensions
from .text_to_board import text_to_board_array, format_board_array_preview
from .settings.service import get_settings_service
from .pages.service import get_page_service
from .schedules.service import get_schedule_service
from .carousels.service import get_carousel_service
from .carousels.models import is_carousel_id

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
    
    def check_and_send_active_page(self) -> bool:
        """Check the active page and send to board if content changed.
        
        Respects schedule mode - uses schedule-based page selection when enabled,
        otherwise falls back to manual active page setting.
            
        Returns:
            True if content was sent to board, False otherwise
        """
        try:
            settings_service = get_settings_service()
            page_service = get_page_service()
            schedule_service = get_schedule_service()
            
            # Determine active page based on schedule mode
            if settings_service.is_schedule_enabled():
                # Schedule mode: Use schedule service to determine page
                # Use TimeService to get current time in configured timezone
                from .time_service import get_time_service
                time_service = get_time_service()
                now = time_service.get_current_time()
                current_time = now.time()
                current_day = now.strftime("%A").lower()  # monday, tuesday, etc.
                
                active_page_id = schedule_service.get_active_page_id(current_time, current_day)
                
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
            
            # Check current silence mode state
            silence_mode_active = Config.is_silence_mode_active()
            entering_silence_mode = silence_mode_active and not self._last_silence_mode_active
            exiting_silence_mode = not silence_mode_active and self._last_silence_mode_active
            
            # Check if board currently has the snoozing indicator
            board_has_indicator = self._last_active_page_content and "snoozing" in self._last_active_page_content
            
            # CRITICAL: If in silence mode BUT board doesn't have indicator yet, allow ONE update
            # This handles power outages, restarts, or any scenario where indicator is missing
            if silence_mode_active and not board_has_indicator:
                logger.info("🔄 Silence mode active but board missing snoozing indicator - allowing update")
                # Will add indicator and send below
            # CRITICAL: If in silence mode AND board already has indicator, BLOCK ALL UPDATES
            elif silence_mode_active and board_has_indicator:
                logger.info("Silence mode active - blocking update to prevent wake-up (indicator already shown)")
                return False
            
            # Get base content
            current_content = result.formatted
            content_to_send = current_content
            
            # Handle entering silence mode - send ONE update with indicator
            if entering_silence_mode:
                logger.info("⏸️  Entering silence mode - sending snoozing indicator")
                content_to_send = current_content
                # Indicator will be added to board array before sending
            
            # Handle exiting silence mode - resume normal operation
            elif exiting_silence_mode:
                logger.info("▶️  Exiting silence mode - resuming normal updates")
                self._snoozing_message_sent = False
                content_to_send = current_content
                # No indicator will be added
            
            # Handle silence mode active but indicator missing (power outage, restart, etc.)
            elif silence_mode_active and not board_has_indicator:
                logger.info("⚡ Silence mode active - ensuring snoozing indicator is displayed")
                content_to_send = current_content
                # Indicator will be added to board array before sending
            
            # Normal mode (not in silence) - check if content changed
            elif not silence_mode_active:
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
            
            # If in silence mode, add "SNOOZING" indicator to bottom right
            if silence_mode_active:
                indicator = "SNOOZING"
                last_row = dims.rows - 1
                start_col = dims.cols - len(indicator)
                for i, char in enumerate(indicator):
                    col = start_col + i
                    if col >= 0:
                        char_code = BoardChars.get_char_code(char)
                        if char_code is not None:
                            board_array[last_row][col] = char_code
            
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
                
                # Mark snoozing message as sent if we sent content WITH indicator during silence mode
                # This covers entering silence mode AND edge cases (restart, power outage, etc.)
                if silence_mode_active and "snoozing" in content_to_send:
                    self._snoozing_message_sent = True
                    logger.info("🔇 Silence mode fully activated - ALL further updates blocked until silence ends")
                # Clear flag when exiting silence mode
                elif exiting_silence_mode:
                    self._snoozing_message_sent = False
                
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
    
    def _get_active_ref_id(self) -> Optional[str]:
        """Return the raw active-page/carousel reference (before carousel resolution)."""
        settings_service = get_settings_service()
        if settings_service.is_schedule_enabled():
            from .time_service import get_time_service
            ts = get_time_service()
            now = ts.get_current_time()
            return get_schedule_service().get_active_page_id(now.time(), now.strftime("%A").lower())
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
