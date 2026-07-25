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


class BoardRuntime:
    """Client + per-board display state for one configured board.

    Introduced by issue #1243: every board FiestaBoard drives gets its own
    ``BoardRuntime`` so per-board caches (last-sent content, silence/snooze
    state, board-read cache) never clobber each other. The ``DisplayService``
    holds ``runtimes: dict[board_id, BoardRuntime]`` and routes every board
    through a single unified per-board path (``check_and_send_for_board``).

    ``config_signature`` lets a hot reload keep an unchanged board's runtime
    (and its caches) instead of rebuilding it — see
    ``DisplayService.rebuild_board_clients``.
    """

    def __init__(self, client: BoardClient | None, board_id):
        self.board_id = board_id
        self.client = client
        self.config_signature = None

        # Active-page send cache (dedupes unchanged sends per board).
        self.last_active_page_content: str | None = None
        self.last_active_page_id: str | None = None

        # Silence-mode state (global decision, per-board delivery).
        self.last_silence_mode_active: bool = False
        self.snoozing_message_sent: bool = False

        # Board-state read cache (populated by the poll thread / adaptive
        # refresh). Board-state polling stays primary-only (see
        # ``_board_poll_loop``), but the cache lives on the runtime so a
        # future per-board poll is a drop-in change.
        self.polled_characters: list[list[int]] | None = None
        self.polled_at: float | None = None

        # Adaptive post-send refresh thread + its cancel event.
        self.refresh_thread: threading.Thread | None = None
        self.refresh_cancel: threading.Event | None = None

        # Collection cadence gate for the run loop: monotonic-ish epoch time
        # of the next collection-boundary check for this board. 0.0 means
        # "check immediately". Only the primary runtime is consulted today.
        self.next_collection_check: float = 0.0


class DisplayService:
    """Main service for displaying information on the board."""

    # Runtime key for the primary board when no board id is available
    # (legacy single-board Config installs, or tests that set ``vb_client``
    # directly without a boards list).
    _PRIMARY_FALLBACK_KEY = "__primary__"

    def __init__(self):
        """Initialize the display service."""
        self.running = True
        # One runtime per configured board (keyed by board id). All per-board
        # display state lives on the runtime; ``self.vb_client`` and the
        # ``self._last_*`` / ``self._polled_*`` attributes are back-compat
        # properties aliasing the PRIMARY board's runtime so untouched callers
        # (api_server.py, mqtt/commands.py) and existing tests keep working.
        self.runtimes: dict[str, BoardRuntime] = {}
        self._primary_board_id = None

        # Board state polling (background thread reads actual board state).
        self._poll_thread: threading.Thread | None = None

    # ------------------------------------------------------------------ #
    # Primary-runtime resolution + back-compat property shims
    # ------------------------------------------------------------------ #

    def _primary_runtime(self) -> BoardRuntime | None:
        """Return the primary board's runtime, or None if none exists yet."""
        if self._primary_board_id is None:
            return None
        return self.runtimes.get(self._primary_board_id)

    def _resolve_primary_key(self):
        """Best-effort key for the primary runtime.

        Prefers the already-established primary id, then the settings SSOT
        (``get_primary_board_id``), then a stable sentinel so setting
        ``vb_client`` always has somewhere to live.
        """
        if self._primary_board_id is not None:
            return self._primary_board_id
        try:
            bid = get_settings_service().get_primary_board_id()
        except Exception:
            bid = None
        return bid if bid else self._PRIMARY_FALLBACK_KEY

    def _ensure_primary_runtime(self) -> BoardRuntime:
        """Return the primary runtime, creating an empty one if needed."""
        rt = self._primary_runtime()
        if rt is None:
            key = self._resolve_primary_key()
            rt = self.runtimes.get(key)
            if rt is None:
                rt = BoardRuntime(client=None, board_id=key)
                self.runtimes[key] = rt
            self._primary_board_id = key
        return rt

    @property
    def vb_client(self) -> BoardClient | None:
        """The primary board's client (kept for single-board code paths)."""
        rt = self._primary_runtime()
        return rt.client if rt is not None else None

    @vb_client.setter
    def vb_client(self, client: BoardClient | None) -> None:
        key = self._resolve_primary_key()
        self._primary_board_id = key
        rt = self.runtimes.get(key)
        if rt is None:
            self.runtimes[key] = BoardRuntime(client=client, board_id=key)
        else:
            rt.client = client

    @property
    def board_clients(self) -> dict:
        """Read-only view {board_id -> client} for callers that iterate boards."""
        return {bid: rt.client for bid, rt in self.runtimes.items() if rt.client is not None}

    def get_board_client(self, board_id) -> BoardClient | None:
        """Return the client for a board id, or None. Seam for per-board send routing (#1244)."""
        rt = self.runtimes.get(board_id)
        return rt.client if rt is not None else None

    # Issue-#1243 wording alias for the same seam.
    get_client = get_board_client

    def get_runtime(self, board_id) -> BoardRuntime | None:
        """Return the runtime for a board id, or None."""
        return self.runtimes.get(board_id)

    # -- State shims aliasing the primary runtime (read + write). --------- #

    @property
    def _last_active_page_content(self):
        rt = self._primary_runtime()
        return rt.last_active_page_content if rt is not None else None

    @_last_active_page_content.setter
    def _last_active_page_content(self, value):
        self._ensure_primary_runtime().last_active_page_content = value

    @property
    def _last_active_page_id(self):
        rt = self._primary_runtime()
        return rt.last_active_page_id if rt is not None else None

    @_last_active_page_id.setter
    def _last_active_page_id(self, value):
        self._ensure_primary_runtime().last_active_page_id = value

    @property
    def _last_silence_mode_active(self) -> bool:
        rt = self._primary_runtime()
        return rt.last_silence_mode_active if rt is not None else False

    @_last_silence_mode_active.setter
    def _last_silence_mode_active(self, value):
        self._ensure_primary_runtime().last_silence_mode_active = value

    @property
    def _snoozing_message_sent(self) -> bool:
        rt = self._primary_runtime()
        return rt.snoozing_message_sent if rt is not None else False

    @_snoozing_message_sent.setter
    def _snoozing_message_sent(self, value):
        self._ensure_primary_runtime().snoozing_message_sent = value

    @property
    def _polled_characters(self):
        rt = self._primary_runtime()
        return rt.polled_characters if rt is not None else None

    @_polled_characters.setter
    def _polled_characters(self, value):
        self._ensure_primary_runtime().polled_characters = value

    @property
    def _polled_at(self):
        rt = self._primary_runtime()
        return rt.polled_at if rt is not None else None

    @_polled_at.setter
    def _polled_at(self, value):
        self._ensure_primary_runtime().polled_at = value

    @property
    def _refresh_thread(self):
        rt = self._primary_runtime()
        return rt.refresh_thread if rt is not None else None

    @_refresh_thread.setter
    def _refresh_thread(self, value):
        self._ensure_primary_runtime().refresh_thread = value

    @property
    def _refresh_cancel(self):
        rt = self._primary_runtime()
        return rt.refresh_cancel if rt is not None else None

    @_refresh_cancel.setter
    def _refresh_cancel(self, value):
        self._ensure_primary_runtime().refresh_cancel = value

    # ------------------------------------------------------------------ #
    # Building / rebuilding runtimes
    # ------------------------------------------------------------------ #

    @staticmethod
    def _config_signature(board: dict) -> tuple:
        """Connection-config signature: unchanged => keep the existing runtime.

        Includes the Local Array Mode tile list (#1399) so editing a tile's
        host/key/enabled state rebuilds the NoteArrayLocalClient.
        """
        tiles = board.get("tiles") or []
        tiles_sig = tuple(sorted(str(t) for t in tiles)) if isinstance(tiles, list) else ()
        return (
            (board.get("api_mode") or "local").lower(),
            board.get("host") or "",
            board.get("port"),
            board.get("local_api_key") or "",
            board.get("cloud_key") or "",
            board.get("note_array_token") or "",
            board.get("device_type") or "flagship",
            board.get("notes_wide") or 1,
            board.get("notes_tall") or 1,
            tiles_sig,
        )

    def _build_board_clients(self, sync_cache: bool = True):
        """Build one runtime per configured board (settings.boards) or fall back to Config.

        Populates ``self.runtimes`` (board_id -> BoardRuntime for every board
        with a usable connection) and ``self._primary_board_id`` (the first
        board, kept for single-board code paths via the ``vb_client``
        property). Unchanged boards keep their existing runtime (and caches)
        so editing one board doesn't reset another's state.

        No credential pre-filter: each device type has its own credential
        field (local_api_key / cloud_key / note_array_token / per-tile local
        keys) and ``board_client_from_board_dict`` already returns None for a
        board without a usable connection. A pre-filter on local/cloud keys
        silently dropped note-array boards (issue #1243 item 3).

        Args:
            sync_cache: read the primary board's current message to seed the
                skip-unchanged cache. Startup wants this; reinitialization
                from an API request must NOT block on board I/O (an
                unreachable board would stall the request), so it skips it.
        """
        settings_service = get_settings_service()
        boards = settings_service.get_board_settings().boards or []

        new_runtimes: dict[str, BoardRuntime] = {}
        for board in boards:
            if not isinstance(board, dict):
                continue
            bid = board.get("id")
            if not bid:
                continue
            sig = self._config_signature(board)
            existing = self.runtimes.get(bid)
            if existing is not None and existing.config_signature == sig and existing.client is not None:
                # Unchanged connection: keep the runtime so its caches survive.
                new_runtimes[bid] = existing
                continue
            client = board_client_from_board_dict(board)
            if client is None:
                continue
            rt = BoardRuntime(client=client, board_id=bid)
            rt.config_signature = sig
            new_runtimes[bid] = rt

        self.runtimes = new_runtimes

        if boards and isinstance(boards[0], dict) and boards[0].get("id") in new_runtimes:
            self._primary_board_id = boards[0]["id"]
        else:
            # Legacy single-board Config path: no usable settings.boards entry.
            use_cloud = Config.BOARD_API_MODE.lower() == "cloud"
            client = BoardClient(
                api_key=Config.get_board_api_key(),
                host=Config.BOARD_HOST if not use_cloud else None,
                use_cloud=use_cloud,
                skip_unchanged=True,
            )
            key = self._PRIMARY_FALLBACK_KEY
            self.runtimes[key] = BoardRuntime(client=client, board_id=key)
            self._primary_board_id = key

        if sync_cache:
            rt = self._primary_runtime()
            if rt is not None and rt.client is not None:
                try:
                    rt.client.read_current_message(sync_cache=True)
                except Exception as e:
                    logger.warning(f"Could not sync cache with board: {e}")

    def rebuild_board_clients(self) -> bool:
        """Rebuild runtimes from current config (diff-based, keyed by board id).

        Prefers settings.boards (one runtime per board with a connection);
        falls back to Config for the primary. Unchanged boards keep their
        runtime + caches; removed/disabled boards are pruned. Must be called
        after any boards-list mutation, otherwise sends keep targeting the old
        connections (issue: content delivered to a removed board).
        """
        logger.info("Rebuilding board clients with updated config...")
        try:
            # sync_cache=False: this runs inside API request handlers, and a
            # blocking read against an unreachable board would stall them.
            self._build_board_clients(sync_cache=False)
            rt = self._primary_runtime()
            if rt is not None and rt.client is not None:
                # Clear stale board-read state from the old config; the poll
                # thread repopulates it on its next iteration.
                rt.polled_characters = None
                rt.polled_at = None
                logger.info(f"Board clients rebuilt successfully ({len(self.runtimes)} runtime(s))")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to rebuild board clients: {e}")
            return False

    # Back-compat alias: external callers + tests use this name.
    reinitialize_board_client = rebuild_board_clients

    def invalidate_board_content(self, board_id: str) -> None:
        """Force the next update cycle to re-send this board's content.

        Clears the board's runtime content dedupe and its client's character
        cache. Used after an out-of-band write to the physical board — e.g.
        the local-array identify flash (#1399) — so the real frame is
        restored on the next poll cycle even though the rendered page
        content hasn't changed.
        """
        rt = self.runtimes.get(board_id)
        if rt is None:
            # Legacy installs may key the primary runtime under the fallback
            # sentinel rather than its settings board id.
            try:
                primary_id = get_settings_service().get_primary_board_id()
            except Exception:
                primary_id = None
            if board_id == primary_id:
                rt = self._primary_runtime()
        if rt is None:
            return
        rt.last_active_page_content = None
        rt.last_active_page_id = None
        if rt.client is not None:
            rt.client.clear_cache()

    # ------------------------------------------------------------------ #
    # Board-state polling (primary board only; state lives on the runtime)
    # ------------------------------------------------------------------ #

    def _get_board_read_interval(self) -> int:
        """Return the board-state read poll interval in seconds based on API mode."""
        polling = get_settings_service().get_polling_settings()
        use_cloud = getattr(self.vb_client, "use_cloud", False) if self.vb_client else False
        return polling.board_read_interval_cloud if use_cloud else polling.board_read_interval_local

    def _board_poll_loop(self) -> None:
        """Background thread: periodically read the primary board's state and cache it.

        Polling stays primary-only (single board-read thread — a thread per
        board would break the single-threaded send invariant the note-array
        >=15s throttle relies on). The cache lives on the primary runtime.
        """
        while self.running:
            interval = self._get_board_read_interval()
            try:
                rt = self._primary_runtime()
                if rt is not None and rt.client is not None:
                    chars = rt.client.read_current_message()
                    if chars:
                        rt.polled_characters = chars
                        rt.polled_at = time.time()
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
        """Adaptively poll the primary board after a send so the cached state
        catches up quickly without waiting for the next full poll interval.

        Strategy: sleep ``initial_delay_seconds``, read the board. If the read
        matches what we just sent, update the cache and stop. Otherwise sleep
        ``retry_interval_seconds`` and try again, until ``max_total_seconds``
        elapses. The latest successful read is always cached.

        A subsequent call cancels any in-flight refresh so rapid sends don't
        stack up threads.
        """
        rt = self._primary_runtime()
        # Cancel any in-flight refresh from a prior send.
        if rt is not None and rt.refresh_cancel is not None:
            rt.refresh_cancel.set()

        if rt is None or rt.client is None:
            return

        client = rt.client
        cancel = threading.Event()
        rt.refresh_cancel = cancel

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
                        rt.polled_characters = chars
                        rt.polled_at = time.time()
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
        rt.refresh_thread = thread
        thread.start()

    def initialize(self) -> bool:
        """Initialize all components."""
        logger.info("Initializing FiestaBoard Display Service...")

        # Validate configuration
        if not Config.validate():
            logger.error("Configuration validation failed")
            return False

        # Initialize board runtimes from settings.boards (all boards) or Config
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

    # ------------------------------------------------------------------ #
    # Per-board display engine (single tick loop)
    # ------------------------------------------------------------------ #

    def check_and_send_active_page(self) -> bool:
        """Drive every configured board from its schedule/active page.

        Back-compat entry point (retained for /refresh, /force-refresh, MQTT,
        the run loop, and existing tests). It drives the PRIMARY board through
        the full feature set (triggers, temporary override, silence indicator,
        per-board active page) and then each secondary board through the same
        unified per-board path. Every board keeps its own state on its runtime.

        Returns:
            True if content was sent to the PRIMARY board, False otherwise.
        """
        primary_id = self._get_first_board_id()
        rt = self._ensure_primary_runtime()
        sent = self.check_and_send_for_board(primary_id, rt, is_primary=True)
        try:
            self._drive_secondary_boards()
        except Exception as e:  # secondaries must never break the primary loop
            logger.error(f"Error updating secondary boards: {e}")
        return sent

    def _drive_secondary_boards(self) -> None:
        """Drive every board after the first through the unified per-board path.

        Each board raising is isolated so one failure never blocks the others.
        """
        settings_service = get_settings_service()
        boards = settings_service.get_board_settings().boards or []
        if len(boards) <= 1:
            return

        for board in boards[1:]:
            if not isinstance(board, dict):
                continue
            board_id = board.get("id")
            if not board_id:
                continue
            rt = self.runtimes.get(board_id)
            if rt is None:
                continue
            if not board.get("enabled", True):
                continue
            try:
                self.check_and_send_for_board(board_id, rt, is_primary=False, board=board)
            except Exception as e:  # partial-failure isolation
                logger.error(f"Board {board_id}: update failed: {e}")

    def check_and_send_for_board(
        self, board_id, rt: BoardRuntime, *, is_primary: bool, board: dict | None = None
    ) -> bool:
        """Resolve and send one board's active page. Unified per-board path.

        Respects schedule mode (per board) - uses schedule-based page selection
        when that board's schedule is enabled, otherwise the board's manual
        active page. Triggers and temporary overrides are the PRIMARY board's
        feature set (locked epic decision); silence is a global decision with
        per-board delivery. All state reads/writes go through ``rt``.

        Returns:
            True if content was sent to this board, False otherwise.
        """
        try:
            settings_service = get_settings_service()
            page_service = get_page_service()
            schedule_service = get_schedule_service()

            # --- Pause short-circuit (issue #970) ---
            # A paused board is completely hands-off: no rotation, no silence
            # indicator, no trigger overrides, no override revert. Evaluate
            # this BEFORE silence. Only a strict ``True`` counts as paused
            # (guards against Mock returns from older fixtures).
            if settings_service.is_paused(board_id=board_id) is True:
                logger.debug("Board %s is paused - skipping update", board_id or "(default)")
                return False

            # --- Silence mode short-circuit (global decision, per-board state) ---
            # Evaluate silence before any plugin/API work so a snoozed board
            # doesn't hit weather/transit/stocks APIs on every poll. We send
            # exactly one update on entering silence, then go quiet.
            silence_mode_active = Config.is_silence_mode_active()
            entering_silence_mode = silence_mode_active and not rt.last_silence_mode_active
            exiting_silence_mode = not silence_mode_active and rt.last_silence_mode_active

            if silence_mode_active and rt.snoozing_message_sent:
                # Steady-state silence: indicator is already on this board.
                logger.debug(
                    "Silence mode active - skipping update (board %s already snoozing)", board_id or "(default)"
                )
                rt.last_silence_mode_active = True
                return False

            if exiting_silence_mode:
                logger.info("▶️  Exiting silence mode - resuming normal updates")
                rt.snoozing_message_sent = False
                # The board still shows the SNOOZING indicator on top of the
                # last-rendered content. Clear the content cache so the next
                # render is unconditionally pushed, otherwise "content
                # unchanged, skipping send" leaves the indicator stuck.
                rt.last_active_page_content = None

            # --- Triggers (PRIMARY only; suppressed during silence) ---
            if is_primary and not silence_mode_active:
                trigger_content = self._check_trigger_override()
                if trigger_content is not None:
                    return self._send_trigger_content(trigger_content, rt)

            # --- Temporary override (PRIMARY only; global consume-once store) ---
            # Issue #949: an explicit user override wins over the silence
            # schedule. Plugin-driven trigger overrides above still defer to
            # silence; only this user-initiated path bypasses it.
            active_page_id = None
            override_active = False
            if is_primary:
                override = settings_service.consume_temporary_override()
                if override is not None:
                    if not override.is_expired():
                        active_page_id = override.page_id
                        override_active = True
                        logger.debug(f"Temporary override active: using page {active_page_id}")
                    elif not silence_mode_active:
                        # Override just expired — apply revert before resuming.
                        # Skip during silence: the silence dispatch owns the
                        # board until the window ends.
                        logger.info(f"Temporary override expired, applying revert: {override.revert_mode}")
                        if override.revert_mode == "blank":
                            return self._send_blank_board(rt)
                        if override.revert_mode == "page" and override.revert_page_id:
                            settings_service.set_active_page_id(override.revert_page_id, board_id=board_id)
                        # "schedule" (and fallback): clear cache so next tick rerenders.
                        rt.last_active_page_content = None

            # --- Determine this board's active page (schedule vs manual) ---
            if active_page_id is None and settings_service.is_schedule_enabled(board_id=board_id):
                from .time_service import get_time_service

                now = get_time_service().get_current_time()
                current_time = now.time()
                current_day = now.strftime("%A").lower()  # monday, tuesday, etc.
                active_page_id = schedule_service.get_active_page_id(current_time, current_day, board_id=board_id)
                if active_page_id:
                    logger.debug(f"Board {board_id}: schedule active page: {active_page_id}")
                else:
                    logger.debug(
                        f"Board {board_id}: no matching schedule for {current_day} {current_time.strftime('%H:%M')}"
                    )
            elif active_page_id is None:
                active_page_id = settings_service.get_active_page_id(board_id=board_id)
                logger.debug(f"Board {board_id}: manual active page: {active_page_id}")

            # Primary never goes dark: default to first page in manual mode.
            # Secondary boards do NOT default (they go dark when no page is set).
            if not active_page_id and is_primary and not settings_service.is_schedule_enabled(board_id=board_id):
                pages = page_service.list_pages()
                if pages:
                    active_page_id = pages[0].id
                    settings_service.set_active_page_id(active_page_id, board_id=board_id)
                    logger.info(f"No active page set, defaulting to first page: {active_page_id}")
                else:
                    logger.debug("No active page and no pages available")
                    return False

            if not active_page_id:
                logger.debug("Board %s: no active page available", board_id or "(default)")
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

            page = page_service.get_page(active_page_id)
            if not page:
                logger.warning(f"Active page not found: {active_page_id}")
                return False

            # Render with fresh data — force_refresh bypasses the preview cache
            # so template variables (weather, time, stocks, etc.) are current.
            result = page_service.preview_page(active_page_id, force_refresh=True)
            if not result or not result.available:
                logger.warning(f"Failed to render active page: {active_page_id}")
                return False

            # --- Silence dispatch (per-board delivery, sized to this board) ---
            # A user-initiated temporary override (primary only) wins over
            # silence (issue #949); everything else is silenced.
            if silence_mode_active and not override_active:
                silence_mode = Config.SILENCE_SCHEDULE_MODE
                if is_primary:
                    silence_dt = self._silence_device_type()
                    silence_nw = silence_nt = 1
                else:
                    silence_dt = (board or {}).get("device_type") or "flagship"
                    silence_nw = (board or {}).get("notes_wide", 1) or 1
                    silence_nt = (board or {}).get("notes_tall", 1) or 1
                if silence_mode == "freeze":
                    if entering_silence_mode:
                        logger.info("⏸️  Entering silence mode (freeze) - leaving board untouched")
                    else:
                        logger.debug("Silence mode active (freeze) - blocking update")
                    rt.last_silence_mode_active = True
                    rt.snoozing_message_sent = True
                    return False
                if silence_mode == "page":
                    return self._send_silence_page(rt)
                return self._send_silence_indicator(silence_dt, rt, silence_nw, silence_nt)

            # --- Normal send (content changed) ---
            current_content = result.formatted
            if current_content == rt.last_active_page_content and active_page_id == rt.last_active_page_id:
                logger.debug("Board %s: content unchanged, skipping send", board_id or "(default)")
                return False
            logger.info(f"Board {board_id}: active page content changed, sending: {active_page_id}")

            if not rt.client:
                logger.warning("Board client not initialized")
                return False

            # Transition settings — page-level if set, otherwise system defaults.
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

            # resolve_dimensions (never get_dimensions, which raises for
            # note_array) so a note-array page renders at its true size.
            dims = resolve_dimensions(page.device_type, page.notes_wide, page.notes_tall)
            board_array = text_to_board_array(current_content, rows=dims.rows, cols=dims.cols)

            success, was_sent = rt.client.send_characters(
                board_array, strategy=strategy, step_interval_ms=interval_ms, step_size=step_size
            )

            if success:
                rt.last_active_page_content = current_content
                rt.last_active_page_id = active_page_id
                rt.last_silence_mode_active = silence_mode_active
                if was_sent:
                    logger.info(f"Board {board_id}: active page sent: {active_page_id}")
                    # Board-state adaptive refresh is primary-only (see
                    # _board_poll_loop). Secondary boards don't feed the
                    # board-read cache the Active Display UI shows.
                    if is_primary:
                        self.request_board_refresh()
                else:
                    logger.debug("Active page unchanged at board level")
                return was_sent
            logger.error(f"Board {board_id}: failed to send active page: {active_page_id}")
            return False

        except Exception as e:
            logger.error(f"Error checking active page for board {board_id}: {e}")
            return False

    # ------------------------------------------------------------------ #
    # Temporary override helpers
    # ------------------------------------------------------------------ #

    def _send_blank_board(self, rt: BoardRuntime | None = None) -> bool:
        """Send a fully blank board when a temporary override expires with revert_mode='blank'."""
        rt = rt if rt is not None else self._ensure_primary_runtime()
        if rt is None or rt.client is None:
            logger.warning("Board client not initialized")
            return False

        device_type = self._silence_device_type()
        dims = get_dimensions(device_type)
        board_array = [[BoardChars.SPACE] * dims.cols for _ in range(dims.rows)]

        settings_service = get_settings_service()
        system_transition = settings_service.get_transition_settings()

        success, was_sent = rt.client.send_characters(
            board_array,
            strategy=system_transition.strategy,
            step_interval_ms=system_transition.step_interval_ms,
            step_size=system_transition.step_size,
        )

        if success:
            rt.last_active_page_content = None
            rt.last_active_page_id = None
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
        """Pick a device type for the primary board's silence display.

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

    def _build_silence_indicator_array(self, device_type: str, notes_wide: int = 1, notes_tall: int = 1):
        """Build a clean board array with 'SNOOZING' centered.

        Sized via resolve_dimensions so it fits the Note (15 cols), the
        Flagship (22 cols), and any note-array grid without overlaying content.
        """
        dims = resolve_dimensions(device_type, notes_wide, notes_tall)
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

    def _send_silence_indicator(
        self, page_device_type: str, rt: BoardRuntime | None = None, notes_wide: int = 1, notes_tall: int = 1
    ) -> bool:
        """Send a clean SNOOZING-only board sized for the device."""
        rt = rt if rt is not None else self._ensure_primary_runtime()
        if rt is None or rt.client is None:
            logger.warning("Board client not initialized")
            return False

        # Primary board: prefer the first configured board's device type
        # (legacy behavior). Secondary boards pass their own resolved geometry.
        if rt.board_id == self._primary_board_id:
            device_type = self._silence_device_type() or page_device_type
        else:
            device_type = page_device_type
        logger.info(f"⏸️  Entering silence mode (indicator) - displaying SNOOZING for {device_type}")

        settings_service = get_settings_service()
        system_transition = settings_service.get_transition_settings()
        board_array = self._build_silence_indicator_array(device_type, notes_wide, notes_tall)

        success, was_sent = rt.client.send_characters(
            board_array,
            strategy=system_transition.strategy,
            step_interval_ms=system_transition.step_interval_ms,
            step_size=system_transition.step_size,
        )

        if success:
            rt.last_active_page_content = "snoozing"
            rt.last_active_page_id = "__silence__"
            rt.last_silence_mode_active = True
            rt.snoozing_message_sent = True
            logger.info("🔇 Silence mode active - further updates blocked until silence ends")
            return was_sent

        logger.error("Failed to send silence indicator to board")
        return False

    def _send_silence_page(self, rt: BoardRuntime | None = None) -> bool:
        """Render the configured silence page once and freeze it on the board.

        Variables in the page are rendered with the values present at the
        moment silence begins; the board is not refreshed afterwards.
        """
        rt = rt if rt is not None else self._ensure_primary_runtime()
        if rt is None or rt.client is None:
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
            return self._send_silence_indicator(self._silence_device_type(), rt)

        logger.info(f"⏸️  Entering silence mode (page) - displaying {page.id}")

        result = page_service.preview_page(page.id, force_refresh=True)
        if not result or not result.available:
            logger.warning("Silence page %s could not be rendered - falling back to indicator", page.id)
            return self._send_silence_indicator(page.device_type, rt)

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

        success, was_sent = rt.client.send_characters(
            board_array,
            strategy=strategy,
            step_interval_ms=interval_ms,
            step_size=step_size,
        )

        if success:
            rt.last_active_page_content = result.formatted
            rt.last_active_page_id = f"__silence_page__:{page.id}"
            rt.last_silence_mode_active = True
            rt.snoozing_message_sent = True
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

    def _send_trigger_content(self, content: str, rt: BoardRuntime | None = None) -> bool:
        """Send trigger content to the board (primary board).

        Returns True if the content was sent successfully.
        """
        rt = rt if rt is not None else self._ensure_primary_runtime()
        if rt is None or rt.client is None:
            logger.warning("Board client not initialized")
            return False

        if content == rt.last_active_page_content:
            logger.debug("Trigger content unchanged, skipping send")
            return False

        logger.info("Sending triggered message to board")
        settings_service = get_settings_service()
        system_transition = settings_service.get_transition_settings()

        dims = get_dimensions(self._silence_device_type())
        board_array = text_to_board_array(content, rows=dims.rows, cols=dims.cols)

        success, was_sent = rt.client.send_characters(
            board_array,
            strategy=system_transition.strategy,
            step_interval_ms=system_transition.step_interval_ms,
            step_size=system_transition.step_size,
        )

        if success:
            rt.last_active_page_content = content
            rt.last_active_page_id = "__trigger__"
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
                # the configured poll_seconds. The gate lives on the primary
                # runtime (issue #1243) so a runtime rebuild resets it cleanly.
                now = time.time()
                primary_rt = self._ensure_primary_runtime()
                if now >= primary_rt.next_collection_check:
                    ref_id = self._get_active_ref_id()
                    if ref_id and is_collection_id(ref_id):
                        collection_service = get_collection_service()
                        secs = collection_service.seconds_until_next_check(ref_id, now)
                        if secs is not None:
                            self.check_and_send_active_page()
                            primary_rt.next_collection_check = now + max(1, secs)
                        else:
                            primary_rt.next_collection_check = now + polling_interval
                    else:
                        primary_rt.next_collection_check = now + polling_interval
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
