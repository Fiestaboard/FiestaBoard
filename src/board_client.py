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
import re
import requests
import threading
import time
from typing import Any, List, Literal, Optional, Tuple

logger = logging.getLogger(__name__)

# Regex pattern to match color markers like {63}, {red}, {/}, {/red}
COLOR_MARKER_PATTERN = re.compile(
    r'\{(?:' +
    r'/?' +  # Optional closing slash
    r'(?:' +
    r'6[3-9]|70|' +  # Numeric codes 63-70
    r'red|orange|yellow|green|blue|violet|purple|white|black' +  # Named colors
    r')?' +  # Color name/code is optional for {/}
    r')\}',
    re.IGNORECASE
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
    return COLOR_MARKER_PATTERN.sub('', text)

# Valid transition strategies
TransitionStrategy = Literal[
    "column",           # Wave - left-to-right
    "reverse-column",   # Drift - right-to-left
    "edges-to-center",  # Curtain - outside-in
    "row",              # Top-to-bottom (API only)
    "diagonal",         # Corner-to-corner (API only)
    "random",           # Random tiles (API only)
    "quietLibrary"      # Row by row, word by word diffing
]

VALID_STRATEGIES = [
    "column", "reverse-column", "edges-to-center", 
    "row", "diagonal", "random", "quietLibrary"
]


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
    if (nrows, ncols) not in _valid_grid_dimensions():
        return False
    for row in rows:
        if not isinstance(row, list) or len(row) != ncols:
            return False
        if not all(isinstance(c, int) for c in row):
            return False
    return True


def parse_read_message_payload(data: Any) -> Optional[List[List[int]]]:
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
    if isinstance(data, dict) and "currentMessage" in data and data.get("currentMessage") is None:
        return True
    return False


class BoardClient:
    """Client for the board with support for Local and Cloud APIs."""
    
    LOCAL_API_PORT = 7000
    CLOUD_API_URL = "https://rw.vestaboard.com/"
    
    def __init__(
        self,
        api_key: str,
        host: Optional[str] = None,
        use_cloud: bool = False,
        skip_unchanged: bool = True,
        port: Optional[int] = None,
    ):
        if not api_key:
            raise ValueError("api_key is required")

        self.api_key = api_key
        self.use_cloud = use_cloud
        self.skip_unchanged = skip_unchanged
        self._port = port if port is not None else self.LOCAL_API_PORT

        if use_cloud:
            self.base_url = self.CLOUD_API_URL
            self.headers = {
                "X-Vestaboard-Read-Write-Key": api_key,
                "Content-Type": "application/json"
            }
            logger.info(f"Board client initialized with Cloud API (skip_unchanged={skip_unchanged})")
        else:
            if not host:
                raise ValueError("host is required for Local API")
            self.host = host
            self.base_url = f"http://{host}:{self._port}/local-api/message"
            self.headers = {
                "X-Vestaboard-Local-Api-Key": api_key,
                "Content-Type": "application/json"
            }
            logger.info(f"Board client initialized with Local API at {host}:{self._port} (skip_unchanged={skip_unchanged})")
        
        self._last_text: Optional[str] = None
        self._last_characters: Optional[List[List[int]]] = None
    
    def send_text(
        self,
        text: str,
        force: bool = False
    ) -> Tuple[bool, bool]:
        clean_text = strip_color_markers(text).upper()
        
        if self.skip_unchanged and not force and self._last_text == clean_text:
            logger.debug("Message unchanged, skipping send")
            return (True, False)
        
        payload = {"text": clean_text}
        
        try:
            response = requests.post(
                self.base_url,
                headers=self.headers,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            
            self._last_text = clean_text
            self._last_characters = None
            api_type = "Cloud API" if self.use_cloud else "Local API"
            logger.info(f"Message sent successfully to board via {api_type}")
            return (True, True)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send message to board: {e}")
            return (False, False)

    def _send_quietlibrary_transition(
        self, 
        target_grid: List[List[int]], 
        step_interval_ms: Optional[int] = None
    ) -> Tuple[bool, bool]:
        """
        Executes a custom quiet transition: word-by-word diffing.
        Runs safely in a background thread to prevent blocking the web UI.
        """
        # Maintain a long delay to prevent the board from dropping payloads while spinning.
        # 14.5 seconds acts as a safe floor to ensure even the longest mechanical rotation completes.
        provided_ms = step_interval_ms or 14500
        delay_sec = max(provided_ms / 1000.0, 14.5)
        
        num_rows = len(target_grid)
        num_cols = len(target_grid[0])
        
        if self._last_characters and len(self._last_characters) == num_rows:
            current_grid = [row[:] for row in self._last_characters]
        else:
            logger.info("QuietLibrary: Local cache empty. Reading actual board state...")
            actual_state = self.read_current_message(sync_cache=True)
            if actual_state and len(actual_state) == num_rows:
                current_grid = [row[:] for row in actual_state]
            else:
                current_grid = [[0] * num_cols for _ in range(num_rows)]
                
        if current_grid == target_grid:
            logger.info("QuietLibrary: Target grid identical to current grid. Skipping.")
            return (True, False)
            
        intermediate_grid = [row[:] for row in current_grid]
        
        # Instantly update cache
        self._last_characters = [row[:] for row in target_grid]
        self._last_text = None
        
        def background_transition():
            logger.info("QuietLibrary background thread: Starting word-by-word transition.")
            request_headers = self.headers.copy()
            request_headers["Connection"] = "close"
            
            try:
                for r in range(num_rows):
                    c = 0
                    while c < num_cols:
                        if intermediate_grid[r][c] != target_grid[r][c]:
                            start_c = c
                            
                            # Group letters into a word
                            if target_grid[r][c] != 0:
                                while c < num_cols and target_grid[r][c] != 0:
                                    c += 1
                                    
                            # Group all trailing spaces attached to the word
                            while c < num_cols and target_grid[r][c] == 0:
                                c += 1
                                
                            # Apply the block (word + spaces)
                            for update_c in range(start_c, c):
                                intermediate_grid[r][update_c] = target_grid[r][update_c]
                                
                            payload = intermediate_grid if self.use_cloud else {"characters": intermediate_grid}
                            
                            logger.info(f"QuietLibrary: Updating row {r}, cols {start_c} to {c - 1}")
                            
                            # Enforce delivery
                            success = False
                            while not success:
                                try:
                                    response = requests.post(
                                        self.base_url, 
                                        headers=request_headers, 
                                        json=payload, 
                                        timeout=10
                                    )
                                    response.raise_for_status()
                                    response.close()
                                    success = True
                                except requests.exceptions.RequestException as e:
                                    logger.warning(f"QuietLibrary: Request failed, retrying. ({e})")
                                    time.sleep(2.0)
                                    
                            # Wait for physical flaps to finish moving
                            time.sleep(delay_sec)
                        else:
                            c += 1
                logger.info("QuietLibrary background transition completed successfully.")
            except Exception as e:
                logger.error(f"QuietLibrary background thread crashed: {e}")

        thread = threading.Thread(target=background_transition)
        thread.daemon = True
        thread.start()
        
        return (True, True)

    def send_characters(
        self,
        characters: List[List[int]],
        strategy: Optional[TransitionStrategy] = None,
        step_interval_ms: Optional[int] = None,
        step_size: Optional[int] = None,
        force: bool = False
    ) -> Tuple[bool, bool]:
        from .devices import DEVICE_DIMENSIONS

        valid_dims = {(d.rows, d.cols) for d in DEVICE_DIMENSIONS.values()}
        num_rows = len(characters)
        num_cols = len(characters[0]) if num_rows > 0 and isinstance(characters[0], list) else 0
        if (num_rows, num_cols) not in valid_dims:
            logger.error(f"Invalid grid: {num_rows}x{num_cols}")
            return (False, False)

        if strategy is not None and strategy not in VALID_STRATEGIES:
            logger.error(f"Invalid strategy: {strategy}")
            return (False, False)
        
        if self.skip_unchanged and not force and self._last_characters == characters:
            return (True, False)

        # --- QUIETLIBRARY INTERCEPT ---
        if strategy == "quietLibrary":
            return self._send_quietlibrary_transition(characters, step_interval_ms)
        # ------------------------------
        
        if self.use_cloud:
            payload = characters
        else:
            payload = {"characters": characters}
            if strategy is not None:
                payload["strategy"] = strategy
            if step_interval_ms is not None:
                payload["step_interval_ms"] = step_interval_ms
            if step_size is not None:
                payload["step_size"] = step_size
        
        try:
            response = requests.post(
                self.base_url,
                headers=self.headers,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            
            self._last_characters = [row[:] for row in characters]
            self._last_text = None
            
            return (True, True)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send character array to board: {e}")
            return (False, False)
    
    def read_current_message(self, sync_cache: bool = False) -> Optional[List[List[int]]]:
        try:
            response = requests.get(
                self.base_url,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            characters = parse_read_message_payload(data)
            
            if sync_cache and characters:
                self._last_characters = [row[:] for row in characters]
                self._last_text = None
            
            return characters
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to read current message: {e}")
            return None
    
    def clear_cache(self) -> None:
        self._last_text = None
        self._last_characters = None
    
    def get_cache_status(self) -> dict:
        return {
            "has_cached_text": self._last_text is not None,
            "has_cached_characters": self._last_characters is not None,
            "skip_unchanged_enabled": self.skip_unchanged,
        }
    
    def would_send(self, text: str = None, characters: List[List[int]] = None) -> bool:
        if not self.skip_unchanged:
            return True
        if text is not None:
            return self._last_text != text
        if characters is not None:
            return self._last_characters != characters
        return True
    
    def test_connection(self) -> bool:
        try:
            result = self.read_current_message()
            return result is not None
        except Exception:
            return False


def board_client_from_board_dict(board: dict) -> Optional["BoardClient"]:
    api_mode = (board.get("api_mode") or "local").lower()
    use_cloud = api_mode == "cloud"
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

FiestaboardClient = BoardClient