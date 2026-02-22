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

import logging
import re
import requests
from typing import Optional, List, Tuple, Literal

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
    "random"            # Random tiles (API only)
]

VALID_STRATEGIES = [
    "column", "reverse-column", "edges-to-center", 
    "row", "diagonal", "random"
]


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
    
    def __init__(
        self,
        api_key: str,
        host: Optional[str] = None,
        use_cloud: bool = False,
        skip_unchanged: bool = True
    ):
        """
        Initialize board API client.
        
        Args:
            api_key: Board API key (Local API key or Read/Write key)
            host: IP or hostname of board for Local API (e.g., "192.168.0.11")
            use_cloud: If True, use Cloud API instead of Local API
            skip_unchanged: If True (default), skip sending if message hasn't changed
        """
        if not api_key:
            raise ValueError("api_key is required")
        
        self.api_key = api_key
        self.use_cloud = use_cloud
        self.skip_unchanged = skip_unchanged
        
        if use_cloud:
            # Cloud API mode
            self.base_url = self.CLOUD_API_URL
            self.headers = {
                "X-Vestaboard-Read-Write-Key": api_key,
                "Content-Type": "application/json"
            }
            logger.info(f"Board client initialized with Cloud API (skip_unchanged={skip_unchanged})")
        else:
            # Local API mode
            if not host:
                raise ValueError("host is required for Local API")
            self.host = host
            self.base_url = f"http://{host}:{self.LOCAL_API_PORT}/local-api/message"
            self.headers = {
                "X-Vestaboard-Local-Api-Key": api_key,
                "Content-Type": "application/json"
            }
            logger.info(f"Board client initialized with Local API at {host} (skip_unchanged={skip_unchanged})")
        
        # Client-side cache to avoid sending unchanged messages
        self._last_text: Optional[str] = None
        self._last_characters: Optional[List[List[int]]] = None
    
    def send_text(
        self,
        text: str,
        force: bool = False
    ) -> Tuple[bool, bool]:
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
        # Strip color markers and convert to uppercase (board requirement)
        clean_text = strip_color_markers(text).upper()
        
        # Check if message has changed (client-side caching)
        if self.skip_unchanged and not force and self._last_text == clean_text:
            logger.debug("Message unchanged, skipping send")
            return (True, False)
        
        # Build payload - text mode doesn't support transitions in Local API
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
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            return (False, False)
    
    def send_characters(
        self,
        characters: List[List[int]],
        strategy: Optional[TransitionStrategy] = None,
        step_interval_ms: Optional[int] = None,
        step_size: Optional[int] = None,
        force: bool = False
    ) -> Tuple[bool, bool]:
        """
        Send message using character array format with optional transitions.
        
        Accepts both Flagship (6x22) and Note (3x15) character arrays.
        
        Args:
            characters: Board character array (6x22 for Flagship, 3x15 for Note)
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
        from .devices import DEVICE_DIMENSIONS

        # Validate grid dimensions against known device types
        valid_dims = {(d.rows, d.cols) for d in DEVICE_DIMENSIONS.values()}
        num_rows = len(characters)
        num_cols = len(characters[0]) if num_rows > 0 and isinstance(characters[0], list) else 0
        if (num_rows, num_cols) not in valid_dims:
            logger.error(
                f"Invalid grid: {num_rows}x{num_cols} is not a supported device size. "
                f"Valid sizes: {sorted(valid_dims)}"
            )
            return (False, False)

        for i, row in enumerate(characters):
            if len(row) != num_cols:
                logger.error(f"Ragged row {i}: expected {num_cols} columns, got {len(row)}")
                return (False, False)
        
        # Validate strategy if provided
        if strategy is not None and strategy not in VALID_STRATEGIES:
            logger.error(f"Invalid strategy: {strategy}. Must be one of {VALID_STRATEGIES}")
            return (False, False)
        
        # Check if characters have changed (client-side caching)
        if self.skip_unchanged and not force and self._last_characters == characters:
            logger.debug("Character array unchanged, skipping send")
            return (True, False)
        
        # Build payload - format differs between Cloud and Local API
        if self.use_cloud:
            # Cloud API (Read/Write API) expects the array directly
            payload = characters
        else:
            # Local API expects {"characters": [...]} with optional transitions
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
            
            transition_info = ""
            if strategy:
                transition_info = f" with {strategy} transition"
                if step_interval_ms:
                    transition_info += f" ({step_interval_ms}ms interval)"
            
            logger.info(f"Character array sent successfully to board{transition_info}")
            return (True, True)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send character array to board: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            return (False, False)
    
    def read_current_message(self, sync_cache: bool = False) -> Optional[List[List[int]]]:
        """
        Read the current message displayed on the board.
        
        Args:
            sync_cache: If True, sync the client cache with the board's current state.
                        This is useful on startup to avoid unnecessary updates.
        
        Returns:
            6x22 character array, or None if failed
        """
        try:
            response = requests.get(
                self.base_url,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            # Local API returns the character array directly
            characters = None
            if isinstance(data, list) and len(data) == 6:
                characters = data
            elif isinstance(data, dict) and "message" in data:
                characters = data.get("message")
            
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
            "cached_text_preview": self._last_text[:50] + "..." if self._last_text and len(self._last_text) > 50 else self._last_text
        }
    
    def would_send(self, text: str = None, characters: List[List[int]] = None) -> bool:
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


# Backward compatibility aliases
FiestaboardClient = BoardClient
