"""Board API client with support for both Local and Cloud APIs.

Supports:
- Local API: Fast updates with transitions (requires local network access)
- Cloud API: Remote access via the board's Read/Write API (internet required)

Local API Reference:
- POST http://{host}:7000/local-api/message - Send message with optional transitions
- GET http://{host}:7000/local-api/message - Read current display

Cloud API Reference:
- POST https://rw.vestaboard.com/ - Send message (text or character array)
- GET https://rw.vestaboard.com/ - Read current display
"""

import json
import logging
import os
import re
import time as _time_module
from collections.abc import Callable
from typing import Any, Literal, Optional

import requests

logger = logging.getLogger(__name__)

# Regex pattern to match color markers like {63}, {red}, {/}, {/red}
COLOR_MARKER_PATTERN = re.compile(
    r"\{(?:"
    + r"/?"  # Optional closing slash
    + r"(?:"
    + r"6[3-9]|70|"  # Numeric codes 63-70
    + r"red|orange|yellow|green|blue|violet|purple|white|black"  # Named colors
    + r")?"  # Color name/code is optional for {/}
    + r")\}",
    re.IGNORECASE,
)


def strip_color_markers(text: str) -> str:
    """Strip color marker codes from text.

    Removes markers like {63}, {red}, {/}, {/red} that are used for
    color tile formatting but would display as literal text on the board
    when using send_text().

    Args:
        text: Text with potential color markers

    Returns:
        Text with color markers removed
    """
    return COLOR_MARKER_PATTERN.sub("", text)


# Valid transition strategies
TransitionStrategy = Literal[
    "column",  # Wave - left-to-right
    "reverse-column",  # Drift - right-to-left
    "edges-to-center",  # Curtain - outside-in
    "row",  # Top-to-bottom (API only)
    "diagonal",  # Corner-to-corner (API only)
    "random",  # Random tiles (API only)
]

VALID_STRATEGIES = ["column", "reverse-column", "edges-to-center", "row", "diagonal", "random"]

# Minimum interval (seconds) between note-array sends enforced client-side.
NOTE_ARRAY_MIN_SEND_INTERVAL: float = 15.0

# Module-level per-board throttle state. Key = note_array_token (board id proxy).
# Persists across BoardClient recreations within a process.
_note_array_last_send: dict[str, float] = {}


def _valid_grid_dimensions() -> set:
    from .devices import DEVICE_DIMENSIONS

    return {(d.rows, d.cols) for d in DEVICE_DIMENSIONS.values()}


def _is_valid_character_grid(rows: Any) -> bool:
    """True if rows is a rectangular int grid matching a known device size."""
    if not isinstance(rows, list) or not rows:
        return False
    first = rows[0]
    if not isinstance(first, list):
        return False
    ncols = len(first)
    nrows = len(rows)
    from .devices import is_valid_note_array_grid

    if (nrows, ncols) not in _valid_grid_dimensions() and not is_valid_note_array_grid(nrows, ncols):
        return False
    for row in rows:
        if not isinstance(row, list) or len(row) != ncols:
            return False
        if not all(isinstance(c, int) for c in row):
            return False
    return True


def parse_read_message_payload(data: Any) -> list[list[int]] | None:
    """Extract character grid from Local or Cloud GET /message (or cloud root) JSON.

    Cloud API returns ``{"currentMessage": {"layout": "<json string>", "id": ...}}``.
    Local API may return a raw grid list or ``{"message": ...}``.
    """
    if isinstance(data, list):
        return data if _is_valid_character_grid(data) else None
    if not isinstance(data, dict):
        return None
    if "message" in data:
        m = data.get("message")
        return m if isinstance(m, list) and _is_valid_character_grid(m) else None
    cm = data.get("currentMessage")
    if isinstance(cm, dict) and "layout" in cm:
        layout = cm.get("layout")
        if layout is None or layout == "":
            return None
        if isinstance(layout, str):
            try:
                layout = json.loads(layout)
            except (json.JSONDecodeError, TypeError):
                return None
        if isinstance(layout, list) and _is_valid_character_grid(layout):
            return layout
    return None


def is_successful_board_read_response(data: Any) -> bool:
    """True if GET body indicates a working read (grid or explicit empty state)."""
    if parse_read_message_payload(data) is not None:
        return True
    return bool(isinstance(data, dict) and "currentMessage" in data and data.get("currentMessage") is None)


class BoardClient:
    """Client for the board with support for Local and Cloud APIs.

    Features:
    - Local API: Fast updates with transition animations (requires local network)
    - Cloud API: Remote access via internet (fallback option)
    - Client-side caching to skip sending unchanged messages
    - Transition animations (Local API only)
    """

    LOCAL_API_PORT = 7000
    CLOUD_API_URL = "https://rw.vestaboard.com/"
    # Note-array Cloud API base URL. Overridable via VESTABOARD_CLOUD_API_URL so a
    # local dev environment can point note-array boards at the mock Cloud server
    # (docker-compose.dev.yml sets it to the fiestaboard-mock-cloud service);
    # defaults to the real Vestaboard Cloud API in production.
    CLOUD_NOTE_ARRAY_API_URL = os.environ.get("VESTABOARD_CLOUD_API_URL") or "https://cloud.vestaboard.com/"

    def __init__(
        self,
        api_key: str,
        host: str | None = None,
        use_cloud: bool = False,
        skip_unchanged: bool = True,
        port: int | None = None,
        note_array_token: str | None = None,
        notes_wide: int = 1,
        notes_tall: int = 1,
        _time_func: Callable[[], float] | None = None,
    ):
        """
        Initialize board API client.

        Args:
            api_key: Board API key (Local API key or Read/Write key)
            host: IP or hostname of board for Local API (e.g., "192.168.0.11")
            use_cloud: If True, use Cloud API instead of Local API
            skip_unchanged: If True (default), skip sending if message hasn't changed
            port: Local API port (default 7000). Used for multi-board e2e (e.g. second board on 7001).
            note_array_token: X-Vestaboard-Token for note-array boards; non-empty enables note-array mode.
            notes_wide: Number of Notes side-by-side (columns = notes_wide * 15).
            notes_tall: Number of Notes stacked (rows = notes_tall * 3).
            _time_func: Injectable monotonic clock for note-array throttle tests.
                Defaults to ``time.monotonic``.
        """
        if not api_key:
            raise ValueError("api_key is required")

        self.api_key = api_key
        self.use_cloud = use_cloud
        self.skip_unchanged = skip_unchanged
        self._port = port if port is not None else self.LOCAL_API_PORT

        if use_cloud:
            # Cloud API mode
            self.base_url = self.CLOUD_API_URL
            self.headers = {"X-Vestaboard-Read-Write-Key": api_key, "Content-Type": "application/json"}
            logger.info(f"Board client initialized with Cloud API (skip_unchanged={skip_unchanged})")
        else:
            # Local API mode
            if not host:
                raise ValueError("host is required for Local API")
            self.host = host
            self.base_url = f"http://{host}:{self._port}/local-api/message"
            self.headers = {"X-Vestaboard-Local-Api-Key": api_key, "Content-Type": "application/json"}
            logger.info(
                f"Board client initialized with Local API at {host}:{self._port} (skip_unchanged={skip_unchanged})"
            )

        # Client-side cache to avoid sending unchanged messages
        self._last_text: str | None = None
        self._last_characters: list[list[int]] | None = None

        # Note-array state. Note arrays are constructed with use_cloud=True, so
        # base_url/headers above point at the RW Cloud API — but when
        # _is_note_array is True the send/read paths OVERRIDE both with the new
        # Cloud API URL + X-Vestaboard-Token, so the RW base_url/headers are unused.
        self._note_array_token: str | None = note_array_token if note_array_token else None
        # notes_wide/notes_tall are carried for downstream dimension enforcement;
        # not yet read in send/read (grid-size enforcement is a follow-up).
        self._notes_wide: int = notes_wide
        self._notes_tall: int = notes_tall
        self._is_note_array: bool = bool(note_array_token)
        # Injectable monotonic clock for the note-array send throttle (tests).
        self._time_func: Callable[[], float] = _time_func if _time_func is not None else _time_module.monotonic

    @property
    def _note_array_headers(self) -> dict[str, str]:
        """Headers for the note-array Cloud API (X-Vestaboard-Token auth)."""
        return {"X-Vestaboard-Token": self._note_array_token, "Content-Type": "application/json"}

    def send_text(self, text: str, force: bool = False) -> tuple[bool, bool]:
        """
        Send plain text message to the board.

        Note: This method automatically:
        - Strips color markers (like {{63}} or {{red}}) - text API doesn't support colors
        - Converts to UPPERCASE - the board only displays uppercase letters

        For transition animations or color support, use send_characters() instead.

        Args:
            text: Plain text message to display (will be uppercased, color markers stripped)
            force: If True, send even if message unchanged (default: False)

        Returns:
            Tuple of (success, was_sent):
            - success: True if message was sent successfully OR skipped because unchanged
            - was_sent: True if message was actually sent to the board
        """
        # Note-array boards use the Cloud API, which is characters-only — there is
        # no text endpoint. Fail clearly instead of POSTing to the wrong (RW) URL.
        if self._is_note_array:
            logger.error("send_text is not supported for note-array boards; use send_characters()")
            return (False, False)

        # Strip color markers and convert to uppercase (board requirement)
        clean_text = strip_color_markers(text).upper()

        # Check if message has changed (client-side caching)
        if self.skip_unchanged and not force and self._last_text == clean_text:
            logger.debug("Message unchanged, skipping send")
            return (True, False)

        # Build payload - text mode doesn't support transitions in Local API
        payload = {"text": clean_text}

        try:
            response = requests.post(self.base_url, headers=self.headers, json=payload, timeout=10)
            response.raise_for_status()

            self._last_text = clean_text
            self._last_characters = None
            api_type = "Cloud API" if self.use_cloud else "Local API"
            logger.info(f"Message sent successfully to board via {api_type}")
            return (True, True)

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send message to board: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            return (False, False)

    def send_characters(
        self,
        characters: list[list[int]],
        strategy: TransitionStrategy | None = None,
        step_interval_ms: int | None = None,
        step_size: int | None = None,
        force: bool = False,
    ) -> tuple[bool, bool]:
        """
        Send message using character array format with optional transitions.

        Accepts Flagship (6x22), Note (3x15), and note-array (variable rows×cols) character arrays.

        Args:
            characters: Board character array (6x22 for Flagship, 3x15 for Note, rows×cols for note-array)
            strategy: Transition animation type:
                - "column": Wave (left-to-right)
                - "reverse-column": Drift (right-to-left)
                - "edges-to-center": Curtain (outside-in)
                - "row": Top-to-bottom (API only)
                - "diagonal": Corner-to-corner (API only)
                - "random": Random tiles (API only)
            step_interval_ms: Delay between animation steps (ms). None = as fast as possible.
            step_size: How many rows/columns animate at once. None = 1 at a time.
            force: If True, send even if characters unchanged (default: False)

        Returns:
            Tuple of (success, was_sent):
            - success: True if message was sent successfully OR skipped because unchanged
            - was_sent: True if message was actually sent to the board
        """
        # Validate grid (accepts flagship, note, and note-array sizes)
        if not _is_valid_character_grid(characters):
            num_rows = len(characters) if isinstance(characters, list) else 0
            num_cols = len(characters[0]) if num_rows > 0 and isinstance(characters[0], list) else 0
            logger.error(f"Invalid grid: {num_rows}x{num_cols} is not a supported device size.")
            return (False, False)

        # Validate strategy if provided
        if strategy is not None and strategy not in VALID_STRATEGIES:
            logger.error(f"Invalid strategy: {strategy}. Must be one of {VALID_STRATEGIES}")
            return (False, False)

        # Note-array boards do not support transitions; strip and warn. Guard on
        # ANY transition param (not just strategy) so a caller passing only
        # step_interval_ms/step_size still gets the debug breadcrumb explaining
        # why their animation param was dropped.
        if self._is_note_array and any(p is not None for p in (strategy, step_interval_ms, step_size)):
            logger.debug(
                "Note-array board: transition params (strategy=%r, step_interval_ms=%r, step_size=%r) "
                "are not supported and will be ignored.",
                strategy,
                step_interval_ms,
                step_size,
            )
            strategy = None
            step_interval_ms = None
            step_size = None

        # Rate-limit note-array sends to >= NOTE_ARRAY_MIN_SEND_INTERVAL seconds.
        # Read the clock once and reuse it for the success-path timestamp below.
        # The check+update below is not locked: FiestaBoard's send paths run on a
        # single-threaded main loop, so the TOCTOU window is unreachable in
        # practice. If sends ever become concurrent, guard this with a per-token lock.
        now = self._time_func() if self._is_note_array else None
        if self._is_note_array:
            last = _note_array_last_send.get(self._note_array_token)
            if last is not None:
                elapsed = now - last
                if elapsed < NOTE_ARRAY_MIN_SEND_INTERVAL:
                    logger.warning(
                        "Note-array send throttled: %.1fs since last send (min %.0fs); skipping.",
                        elapsed,
                        NOTE_ARRAY_MIN_SEND_INTERVAL,
                    )
                    return (True, False)

        # Check if characters have changed (client-side caching)
        if self.skip_unchanged and not force and self._last_characters == characters:
            logger.debug("Character array unchanged, skipping send")
            return (True, False)

        # Build payload - format differs by API type
        if self._is_note_array:
            # Note-array Cloud API: POST {"characters": grid} to cloud.vestaboard.com
            payload = {"characters": characters}
        elif self.use_cloud:
            # RW Cloud API: sends the array directly (no wrapper)
            payload = characters
        else:
            # Local API: {"characters": [...]} with optional transitions
            payload = {"characters": characters}
            if strategy is not None:
                payload["strategy"] = strategy
            if step_interval_ms is not None:
                payload["step_interval_ms"] = step_interval_ms
            if step_size is not None:
                payload["step_size"] = step_size

        try:
            if self._is_note_array:
                url = self.CLOUD_NOTE_ARRAY_API_URL
                hdrs = self._note_array_headers
            else:
                url = self.base_url
                hdrs = self.headers
            response = requests.post(url, headers=hdrs, json=payload, timeout=10)
            response.raise_for_status()

            self._last_characters = [row[:] for row in characters]
            self._last_text = None

            if self._is_note_array:
                _note_array_last_send[self._note_array_token] = now

            transition_info = ""
            if strategy:
                transition_info = f" with {strategy} transition"
                if step_interval_ms:
                    transition_info += f" ({step_interval_ms}ms interval)"

            logger.info(f"Character array sent successfully to board{transition_info}")
            return (True, True)

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send character array to board: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            return (False, False)

    def read_current_message(self, sync_cache: bool = False) -> list[list[int]] | None:
        """
        Read the current message displayed on the board.

        Args:
            sync_cache: If True, sync the client cache with the board's current state.
                        This is useful on startup to avoid unnecessary updates.

        Returns:
            Character grid sized to the board (Flagship 6x22, Note 3x15, or a
            note array's rows x cols), or None if failed or empty.
        """
        try:
            if self._is_note_array:
                url = self.CLOUD_NOTE_ARRAY_API_URL
                hdrs = self._note_array_headers
            else:
                url = self.base_url
                hdrs = self.headers
            response = requests.get(url, headers=hdrs, timeout=10)
            response.raise_for_status()
            data = response.json()
            characters = parse_read_message_payload(data)

            # Optionally sync the cache with current board state
            if sync_cache and characters:
                self._last_characters = [row[:] for row in characters]
                self._last_text = None
                logger.info("Cache synced with current board state")

            return characters

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to read current message: {e}")
            return None

    def clear_cache(self) -> None:
        """Clear the client-side message cache, forcing the next send to go through."""
        self._last_text = None
        self._last_characters = None
        logger.debug("Message cache cleared")

    def get_cache_status(self) -> dict:
        """Get the current cache status for debugging/monitoring."""
        return {
            "has_cached_text": self._last_text is not None,
            "has_cached_characters": self._last_characters is not None,
            "skip_unchanged_enabled": self.skip_unchanged,
            "cached_text_preview": self._last_text[:50] + "..."
            if self._last_text and len(self._last_text) > 50
            else self._last_text,
        }

    def would_send(self, text: str | None = None, characters: list[list[int]] | None = None) -> bool:
        """
        Check if a message would actually be sent (i.e., is it different from cached).

        Useful for UI to show if an update would cause a board refresh.

        Args:
            text: Text message to check
            characters: Character array to check

        Returns:
            True if message differs from cache and would be sent
        """
        if not self.skip_unchanged:
            return True

        if text is not None:
            return self._last_text != text
        if characters is not None:
            return self._last_characters != characters
        return True

    def test_connection(self) -> bool:
        """
        Test the connection to the board.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            result = self.read_current_message()
            return result is not None
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False


def board_client_from_board_dict(board: dict) -> Optional["BoardClient"]:
    """Build a board client from a board instance dict (e.g. from settings.boards).

    Args:
        board: Dict with api_mode, host, port (optional), local_api_key, cloud_key.

    Returns:
        BoardClient (or a duck-type compatible NoteArrayLocalClient for
        local-mode note arrays) if the board has connection configured,
        None otherwise.
    """
    api_mode = (board.get("api_mode") or "local").lower()
    use_cloud = api_mode == "cloud"

    # Note-array boards: detected by device_type (not api_mode).
    # Local mode (api_mode == "local" with saved tiles) fans out per-tile
    # local POSTs; otherwise they use the Cloud API with X-Vestaboard-Token.
    from .devices import BoardInstance, is_note_array

    device_type = board.get("device_type") or "flagship"
    if is_note_array(device_type):
        instance = BoardInstance.from_dict(board)
        if instance.uses_local_tiles:
            from .note_array_local_client import NoteArrayLocalClient

            tiles = instance.configured_tiles()
            if not tiles:
                return None
            return NoteArrayLocalClient(tiles, instance.notes_wide, instance.notes_tall)
        token = board.get("note_array_token") or ""
        if not token:
            return None
        notes_wide = board.get("notes_wide") or 1
        notes_tall = board.get("notes_tall") or 1
        # api_key is required by BoardClient.__init__ but unused for note arrays;
        # pass the token as api_key to satisfy the non-empty guard.
        return BoardClient(
            api_key=token,
            host=None,
            use_cloud=True,
            skip_unchanged=True,
            note_array_token=token,
            notes_wide=notes_wide,
            notes_tall=notes_tall,
        )

    if use_cloud:
        key = board.get("cloud_key") or ""
        if not key:
            return None
        return BoardClient(api_key=key, host=None, use_cloud=True, skip_unchanged=True)
    key = board.get("local_api_key") or ""
    host = board.get("host") or ""
    if not key or not host:
        return None
    port = board.get("port")
    if port is not None and not isinstance(port, int):
        try:
            port = int(port)
        except (TypeError, ValueError):
            port = None
    return BoardClient(
        api_key=key,
        host=host,
        use_cloud=False,
        skip_unchanged=True,
        port=port,
    )


# Backward compatibility aliases
FiestaboardClient = BoardClient
