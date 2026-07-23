"""Main application entry point for FiestaBoard Display Service."""

import logging
import signal
import threading
import time

import schedule

from .board_chars import BoardChars
from .board_client import BoardClient, board_client_from_board_dict
from .collections.models import is_collection_id
from .collections.service import get_collection_service
from .config import Config
from .devices import get_dimensions, resolve_dimensions
from .pages.service import get_page_service
from .schedules.service import get_schedule_service
from .settings.service import get_settings_service
from .text_to_board import text_to_board_array
from .triggers.service import get_trigger_service

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger(__name__)


class DisplayService:
    """Main service for displaying information on the board."""

    def __init__(self):
        """Initialize the display service."""
        self.running = True
        self.vb_client: BoardClient | None = None
        # One client per configured board (keyed by board id). ``vb_client``
        # stays the first board's client for the many single-board code
        # paths (manual send, debug, plugins); the update loop uses this map
        # to drive secondary boards. See issue #1243.
        self.board_clients: dict[str, BoardClient] = {}

        # Active page polling state
        self._last_active_page_content: str | None = None
        self._last_active_page_id: str | None = None
        self._last_silence_mode_active: bool = False
        self._snoozing_message_sent: bool = False
        # Per-secondary-board content cache: board_id -> (page_id, content).
        # Mirrors _last_active_page_* for the primary board.
        self._secondary_last_sent: dict[str, tuple[str, str]] = {}

        # Board state polling (background thread reads actual board state)
        self._polled_characters: list[list[int]] | None = None
        self._polled_at: float | None = None
        self._poll_thread: threading.Thread | None = None
        # Adaptive post-send refresh: a background thread polls the board
        # on a short ramp after each send and stops early once the read
        # matches what we just sent. ``_refresh_cancel`` lets a subsequent
        # call abort an in-flight cycle so rapid sends don't pile up.
        self._refresh_thread: threading.Thread | None = None
        self._refresh_cancel: threading.Event | None = None

    def _build_board_clients(self, sync_cache: bool = True):
        """Build one client per configured board (settings.boards) or fall back to Config.

        Sets ``self.board_clients`` (board_id -> client for every board with
        connection credentials) and ``self.vb_client`` (the first board's
        client, kept for single-board code paths).

        Args:
            sync_cache: read the primary board's current message to seed the
                skip-unchanged cache. Startup wants this; reinitialization
                from an API request must NOT block on board I/O (an
                unreachable board would stall the request), so it skips it —
                a cold cache just means the next send isn't deduplicated.
        """
        settings_service = get_settings_service()
        boards = settings_service.get_board_settings().boards or []
        clients: dict[str, BoardClient] = {}
        for board in boards:
            # No credential pre-filter here: each device type has its own
            # credential field (local_api_key / cloud_key / note_array_token)
            # and board_client_from_board_dict already returns None for a
            # board without a usable connection. A pre-filter on local/cloud
            # keys silently dropped note-array boards (issue #1243 item 3).
            client = board_client_from_board_dict(board)
            if client and board.get("id"):
                self._attach_transition_runner(client)
                clients[board["id"]] = client
        self.board_clients = clients
        if boards and boards[0].get("id") in clients:
            self.vb_client = clients[boards[0]["id"]]
        else:
            use_cloud = Config.BOARD_API_MODE.lower() == "cloud"
            self.vb_client = BoardClient(
                api_key=Config.get_board_api_key(),
                host=Config.BOARD_HOST if not use_cloud else None,
                use_cloud=use_cloud,
                skip_unchanged=True,
            )
            self._attach_transition_runner(self.vb_client)
        if sync_cache:
            try:
                self.vb_client.read_current_message(sync_cache=True)
            except Exception as e:
                logger.warning(f"Could not sync cache with board: {e}")

    @staticmethod
    def _attach_transition_runner(client: BoardClient) -> None:
        """Attach the global transition runner so render("plugin:...") works.

        Imports are local so test scaffolding can build clients without
        pulling in the plugin registry.
        """
        try:
            from .plugins.registry import get_plugin_registry
            from .transitions import TransitionRunner

            registry = get_plugin_registry()
            runner = TransitionRunner(resolver=registry.get_transition_plugin)
            client.set_transition_runner(runner)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"Could not attach transition runner: {exc}")

    def reinitialize_board_client(self) -> bool:
        """Reinitialize all board clients with current config.

        Prefers settings.boards (one client per board with connection);
        falls back to Config for the primary. Must be called after any
        boards-list mutation, otherwise sends keep targeting the old
        connections (issue: content delivered to a removed board).
        """
        logger.info("Reinitializing board clients with updated config...")
        try:
            # sync_cache=False: reinit runs inside API request handlers, and a
            # blocking read against an unreachable board would stall them.
            self._build_board_clients(sync_cache=False)
            if self.vb_client:
                # Clear stale polled state from the old config; poll thread will
                # populate it again on its next iteration using the new client.
                self._polled_characters = None
                self._polled_at = None
                # Drop per-board content caches for boards that no longer exist
                # (or whose connection may have changed).
                self._secondary_last_sent = {
                    board_id: sent
                    for board_id, sent in self._secondary_last_sent.items()
                    if board_id in self.board_clients
                }
                logger.info(f"Board clients reinitialized successfully ({len(self.board_clients)} board(s))")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to reinitialize board client: {e}")
            return False

    def invalidate_board_content(self, board_id: str) -> None:
        """Force the next update cycle to re-send this board's content.

        Clears the display loop's content dedupe for the board (primary or
        secondary) and the board client's character cache. Used after an
        out-of-band write to the physical board — e.g. the local-array
        identify flash — so the real frame is restored on the next poll
        cycle even though the rendered page content hasn't changed.
        """
        primary_id = get_settings_service().get_primary_board_id()
        if board_id == primary_id:
            self._last_active_page_content = None
        self._secondary_last_sent.pop(board_id, None)
        client = self.board_clients.get(board_id)
        if client is not None:
            client.clear_cache()

    def _get_board_read_interval(self) -> int:
        """Return the board-state read poll interval in seconds based on API mode."""
        polling = get_settings_service().get_polling_settings()
        use_cloud = getattr(self.vb_client, "use_cloud", False) if self.vb_client else False
        return polling.board_read_interval_cloud if use_cloud else polling.board_read_interval_local

    def _board_poll_loop(self) -> None:
        """Background thread: periodically read actual board state and cache it."""
        while self.running:
            interval = self._get_board_read_interval()
            try:
                if self.vb_client:
                    chars = self.vb_client.read_current_message()
                    if chars:
                        self._polled_characters = chars
                        self._polled_at = time.time()
                        logger.debug("Board state poll succeeded")
            except Exception as e:
                logger.debug(f"Board state poll failed: {e}")
            time.sleep(interval)

    def request_board_refresh(
        self,
        initial_delay_seconds: float = 0.5,
        retry_interval_seconds: float = 1.0,
        max_total_seconds: float = 3.0,
    ) -> None:
        """Adaptively poll the board after a send so the cached state catches up
        quickly without waiting for the next full poll interval.

        Strategy: sleep ``initial_delay_seconds``, read the board. If the read
        matches what we just sent, update the cache and stop. Otherwise sleep
        ``retry_interval_seconds`` and try again, until ``max_total_seconds``
        elapses. The latest successful read is always cached, so the display
        cache improves even when we never observe a match (e.g. during a long
        transition animation).

        A subsequent call cancels any in-flight refresh so rapid sends don't
        stack up threads.
        """
        # Cancel any in-flight refresh from a prior send.
        if self._refresh_cancel is not None:
            self._refresh_cancel.set()

        client = self.vb_client
        if client is None:
            return

        cancel = threading.Event()
        self._refresh_cancel = cancel

        # Snapshot what we just sent so we can detect when the board has
        # caught up. May be None if no send has happened on this client yet.
        last_sent = getattr(client, "_last_characters", None)
        expected = [row[:] for row in last_sent] if isinstance(last_sent, list) and last_sent else None

        def _do_refresh() -> None:
            start = time.monotonic()
            if cancel.wait(initial_delay_seconds):
                return
            while True:
                try:
                    chars = client.read_current_message()
                    if chars:
                        self._polled_characters = chars
                        self._polled_at = time.time()
                        if expected is not None and chars == expected:
                            logger.debug("Post-send refresh: board state matches sent content")
                            return
                except Exception as e:
                    logger.debug(f"Post-send board state refresh failed: {e}")

                elapsed = time.monotonic() - start
                if elapsed >= max_total_seconds:
                    return
                wait_secs = min(retry_interval_seconds, max_total_seconds - elapsed)
                if cancel.wait(wait_secs):
                    return

        thread = threading.Thread(target=_do_refresh, daemon=True)
        self._refresh_thread = thread
        thread.start()

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
                logger.info(
                    f"Default transition: {transition['strategy']} (interval={transition['step_interval_ms']}ms, step_size={transition['step_size']})"
                )
        except Exception as e:
            logger.error(f"Failed to initialize board client: {e}")
            return False

        # Start background thread that reads the actual board state periodically
        self._poll_thread = threading.Thread(target=self._board_poll_loop, daemon=True, name="board-state-poll")
        self._poll_thread.start()
        interval = self._get_board_read_interval()
        logger.info(f"Board state poll started (interval={interval}s)")

        # Log configuration summary
        summary = Config.get_summary()
        logger.info(f"Configuration: {summary}")

        return True

    @staticmethod
    def _get_first_board_id() -> str | None:
        """Return the ID of the primary (first) configured board, or None."""
        return get_settings_service().get_primary_board_id()

    def check_and_send_active_page(self) -> bool:
        """Update every configured board from its schedule/active page.

        The primary board (boards[0]) keeps the full feature set — triggers,
        temporary overrides, silence indicator, manual active page. Secondary
        boards are schedule-driven (issue #1243): each enabled, unpaused,
        schedule-enabled board resolves its own active page and receives it
        via its own client.

        Returns:
            True if content was sent to the primary board, False otherwise
        """
        sent = self._update_primary_board()
        try:
            self._update_secondary_boards()
        except Exception as e:  # secondaries must never break the primary loop
            logger.error(f"Error updating secondary boards: {e}")
        return sent

    def _update_secondary_boards(self) -> None:
        """Drive every board after the first from its own schedule.

        Scope (first slice of #1243): schedule + per-board default page,
        per-board pause and schedule_enabled, collections, per-page
        transitions. Global silence mode silences secondaries entirely
        (freeze semantics — the SNOOZING indicator stays a primary-board
        feature). Triggers, temporary overrides and the manual active page
        remain primary-only.
        """
        settings_service = get_settings_service()
        boards = settings_service.get_board_settings().boards or []
        if len(boards) <= 1:
            return
        if Config.is_silence_mode_active():
            return

        page_service = get_page_service()
        schedule_service = get_schedule_service()
        collection_service = get_collection_service()
        from .time_service import get_time_service

        now = get_time_service().get_current_time()
        current_time = now.time()
        current_day = now.strftime("%A").lower()

        for board in boards[1:]:
            board_id = board.get("id")
            if not board_id:
                continue
            client = self.board_clients.get(board_id)
            if client is None:
                continue
            if not board.get("enabled", True):
                continue
            if settings_service.is_paused(board_id=board_id) is True:
                continue
            if not settings_service.is_schedule_enabled(board_id=board_id):
                continue

            active_page_id = schedule_service.get_active_page_id(current_time, current_day, board_id=board_id)
            if not active_page_id:
                continue
            if is_collection_id(active_page_id):
                active_page_id = collection_service.resolve_page_id(active_page_id)
                if not active_page_id:
                    continue

            page = page_service.get_page(active_page_id)
            if not page:
                logger.warning(f"Board {board_id}: active page not found: {active_page_id}")
                continue
            result = page_service.preview_page(active_page_id, force_refresh=True)
            if not result or not result.available:
                logger.warning(f"Board {board_id}: failed to render active page: {active_page_id}")
                continue

            content = result.formatted
            if self._secondary_last_sent.get(board_id) == (active_page_id, content):
                continue

            system_transition = settings_service.get_transition_settings()
            strategy = page.transition_strategy if page.transition_strategy else system_transition.strategy
            interval_ms = (
                page.transition_interval_ms
                if page.transition_interval_ms is not None
                else system_transition.step_interval_ms
            )
            step_size = (
                page.transition_step_size if page.transition_step_size is not None else system_transition.step_size
            )

            dims = resolve_dimensions(page.device_type, page.notes_wide, page.notes_tall)
            board_array = text_to_board_array(content, rows=dims.rows, cols=dims.cols)
            try:
                success, was_sent = client.render(
                    board_array,
                    strategy=strategy,
                    step_interval_ms=interval_ms,
                    step_size=step_size,
                    device_type=page.device_type,
                )
            except Exception as e:
                logger.error(f"Board {board_id}: send failed: {e}")
                continue
            if success:
                self._secondary_last_sent[board_id] = (active_page_id, content)
                if was_sent:
                    logger.info(f"Board {board_id}: active page sent: {active_page_id}")
            else:
                logger.error(f"Board {board_id}: failed to send active page: {active_page_id}")

    def _update_primary_board(self) -> bool:
        """Check the primary board's active page and send if content changed.

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

            # --- Pause short-circuit (issue #970) ---
            # When the board is paused the user wants FiestaBoard to be
            # completely hands-off: no scheduled rotation, no silence
            # indicator, no trigger overrides, no override revert. Evaluate
            # this BEFORE silence so a paused board doesn't even emit the
            # one-shot SNOOZING indicator on entering silence.
            board_id = self._get_first_board_id()
            # Only treat a strict ``True`` as paused — guards against Mock
            # returns from older fixtures that pre-date the pause feature.
            if settings_service.is_paused(board_id=board_id) is True:
                logger.debug("Board %s is paused - skipping update", board_id or "(default)")
                return False

            # --- Silence mode short-circuit (evaluated FIRST) ---
            # Important: we evaluate silence before doing ANY plugin/API work
            # (trigger evaluation, page rendering, collection resolution) so a
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

            # --- Temporary override check (user-initiated, time-limited; below triggers) ---
            # Issue #949: an explicit user override (POST /settings/temporary-override)
            # must win over the silence schedule. The user pressed "show this page
            # now" — honoring silence here would silently swallow that intent.
            # Plugin-driven trigger overrides above DO still defer to silence;
            # only this user-initiated path bypasses it.
            active_page_id = None
            override_active = False
            override = settings_service.consume_temporary_override()
            if override is not None:
                if not override.is_expired():
                    active_page_id = override.page_id
                    override_active = True
                    logger.debug(f"Temporary override active: using page {active_page_id}")
                elif not silence_mode_active:
                    # Override just expired — apply revert before resuming normal flow.
                    # Skip during silence: the silence-mode dispatch below will own
                    # the board until the silence window ends.
                    logger.info(f"Temporary override expired, applying revert: {override.revert_mode}")
                    if override.revert_mode == "blank":
                        return self._send_blank_board()
                    if override.revert_mode == "page" and override.revert_page_id:
                        settings_service.set_active_page_id(override.revert_page_id)
                    # "schedule" (and fallback): clear content cache so next tick rerenders
                    self._last_active_page_content = None

            # Determine active page based on schedule mode (skipped when override is active)
            if active_page_id is None and settings_service.is_schedule_enabled():
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
                    logger.debug(
                        f"Schedule mode: No matching schedule for {current_day} {current_time.strftime('%H:%M')}"
                    )
            elif active_page_id is None:
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

            # Resolve collections: if the active ref is a collection, determine
            # which underlying page should be shown right now.
            collection_service = get_collection_service()
            if is_collection_id(active_page_id):
                resolved = collection_service.resolve_page_id(active_page_id)
                if not resolved:
                    logger.warning(f"Collection not found or empty: {active_page_id}")
                    return False
                logger.debug(f"Collection {active_page_id} resolved to page {resolved}")
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
            #
            # Exception (issue #949): a user-initiated temporary override wins
            # over silence. The user explicitly asked to see this page now, so
            # we render it and skip the silence dispatch. Once the override
            # expires, normal silence behavior resumes on the next tick.
            if silence_mode_active and not override_active:
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
            if current_content == self._last_active_page_content and active_page_id == self._last_active_page_id:
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
            interval_ms = (
                page.transition_interval_ms
                if page.transition_interval_ms is not None
                else system_transition.step_interval_ms
            )
            step_size = (
                page.transition_step_size if page.transition_step_size is not None else system_transition.step_size
            )

            # Send to board
            dims = resolve_dimensions(page.device_type, page.notes_wide, page.notes_tall)
            board_array = text_to_board_array(content_to_send, rows=dims.rows, cols=dims.cols)

            success, was_sent = self.vb_client.render(
                board_array,
                strategy=strategy,
                step_interval_ms=interval_ms,
                step_size=step_size,
                device_type=page.device_type,
            )

            if success:
                self._last_active_page_content = content_to_send
                self._last_active_page_id = active_page_id
                self._last_silence_mode_active = silence_mode_active

                if was_sent:
                    logger.info(f"Active page sent to board: {active_page_id}")
                    self.request_board_refresh()
                else:
                    logger.debug("Active page unchanged at board level")
                return was_sent
            logger.error(f"Failed to send active page to board: {active_page_id}")
            return False

        except Exception as e:
            logger.error(f"Error checking active page: {e}")
            return False

    # ------------------------------------------------------------------ #
    # Temporary override helpers
    # ------------------------------------------------------------------ #

    def _send_blank_board(self) -> bool:
        """Send a fully blank board when a temporary override expires with revert_mode='blank'."""
        if not self.vb_client:
            logger.warning("Board client not initialized")
            return False

        device_type = self._silence_device_type()
        dims = get_dimensions(device_type)
        board_array = [[BoardChars.SPACE] * dims.cols for _ in range(dims.rows)]

        settings_service = get_settings_service()
        system_transition = settings_service.get_transition_settings()

        success, was_sent = self.vb_client.render(
            board_array,
            strategy=system_transition.strategy,
            step_interval_ms=system_transition.step_interval_ms,
            step_size=system_transition.step_size,
            device_type=device_type,
        )

        if success:
            self._last_active_page_content = None
            self._last_active_page_id = None
            logger.info("Temporary override expired (blank) - board cleared")
            if was_sent:
                self.request_board_refresh()
        else:
            logger.error("Failed to send blank board after temporary override expiry")
        return success

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

        success, was_sent = self.vb_client.render(
            board_array,
            strategy=system_transition.strategy,
            step_interval_ms=system_transition.step_interval_ms,
            step_size=system_transition.step_size,
            device_type=device_type,
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
            logger.warning("Silence page %s could not be rendered - falling back to indicator", page.id)
            return self._send_silence_indicator(page.device_type)

        settings_service = get_settings_service()
        system_transition = settings_service.get_transition_settings()
        strategy = page.transition_strategy or system_transition.strategy
        interval_ms = (
            page.transition_interval_ms
            if page.transition_interval_ms is not None
            else system_transition.step_interval_ms
        )
        step_size = page.transition_step_size if page.transition_step_size is not None else system_transition.step_size

        dims = resolve_dimensions(page.device_type, page.notes_wide, page.notes_tall)
        board_array = text_to_board_array(result.formatted, rows=dims.rows, cols=dims.cols)

        success, was_sent = self.vb_client.render(
            board_array,
            strategy=strategy,
            step_interval_ms=interval_ms,
            step_size=step_size,
            device_type=page.device_type,
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

    def _check_trigger_override(self) -> str | None:
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
            for _plugin_id, plugin in registry.trigger_plugins.items():
                trigger_service.check_plugin_triggers(plugin)

            active = trigger_service.get_active_trigger()
            if active is None:
                return None

            # If the plugin has a trigger_page_id configured, render that page
            # with the trigger's data as template context instead of the hard-coded display.
            plugin = registry.get_plugin(active.plugin_id)
            if plugin:
                trigger_page_id = plugin.config.get("trigger_page_id")
                if trigger_page_id:
                    from .pages.service import get_page_service

                    page_service = get_page_service()
                    page = page_service.get_page(trigger_page_id)
                    if page and page.type == "template":
                        context = {active.plugin_id: active.data} if active.data else None
                        result = page_service.render_page(page, context=context)
                        if result.available and result.formatted:
                            return result.formatted

            # Fall back to the plugin's built-in formatted display
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

        device_type = self._silence_device_type()
        dims = get_dimensions(device_type)
        board_array = text_to_board_array(content, rows=dims.rows, cols=dims.cols)

        success, was_sent = self.vb_client.render(
            board_array,
            strategy=system_transition.strategy,
            step_interval_ms=system_transition.step_interval_ms,
            step_size=system_transition.step_size,
            device_type=device_type,
        )

        if success:
            self._last_active_page_content = content
            self._last_active_page_id = "__trigger__"
            if was_sent:
                logger.info("Triggered message sent to board")
            return was_sent
        logger.error("Failed to send triggered message to board")
        return False

    def _get_active_ref_id(self) -> str | None:
        """Return the raw active-page/collection reference (before collection resolution)."""
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
        _next_collection_check: float = time.time()
        try:
            while self.running:
                schedule.run_pending()

                # 1-second silence-boundary detector. The schedule library only
                # fires check_and_send_active_page every polling_interval seconds,
                # so without this the silence page could appear up to ~15s after
                # the configured start time (longer if the user raised the poll
                # interval). A cheap is_silence_mode_active() call each second
                # lets us catch the transition within ~1s.
                try:
                    silence_now = Config.is_silence_mode_active()
                except Exception as e:
                    logger.debug(f"Silence boundary check failed: {e}")
                    silence_now = self._last_silence_mode_active
                if silence_now != self._last_silence_mode_active:
                    logger.debug(
                        "Silence boundary crossed (now=%s, was=%s) - forcing immediate update",
                        silence_now,
                        self._last_silence_mode_active,
                    )
                    self.check_and_send_active_page()

                # When a collection is active, poll at its mode-specific cadence:
                # time-mode aligns with the next page boundary; variable-mode uses
                # the configured poll_seconds.
                now = time.time()
                if now >= _next_collection_check:
                    ref_id = self._get_active_ref_id()
                    if ref_id and is_collection_id(ref_id):
                        collection_service = get_collection_service()
                        secs = collection_service.seconds_until_next_check(ref_id, now)
                        if secs is not None:
                            self.check_and_send_active_page()
                            _next_collection_check = now + max(1, secs)
                        else:
                            _next_collection_check = now + polling_interval
                    else:
                        _next_collection_check = now + polling_interval
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
