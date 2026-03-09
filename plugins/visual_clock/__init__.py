"""Visual Clock plugin for FiestaBoard.

Displays a full-screen clock with large pixel-art style digits
that span the 6x22 board grid.
"""

from typing import Any, Dict, List
import logging
from datetime import datetime
import pytz

from src.plugins.base import PluginBase, PluginResult
from src.board_chars import BoardChars

logger = logging.getLogger(__name__)

# Board dimensions
ROWS = 6
COLS = 22

# Digit dimensions (6 rows tall, 4 columns wide) - full board height
DIGIT_HEIGHT = 6
DIGIT_WIDTH = 4

# Colon dimensions (5 rows tall, 2 columns wide)
COLON_WIDTH = 2

# Color code mapping
COLOR_MAP = {
    "red": BoardChars.RED,
    "orange": BoardChars.ORANGE,
    "yellow": BoardChars.YELLOW,
    "green": BoardChars.GREEN,
    "blue": BoardChars.BLUE,
    "violet": BoardChars.VIOLET,
    "white": BoardChars.WHITE,
    "black": BoardChars.BLACK,
}

# Color patterns - define colors for each of the 5 elements (h1, h2, colon, m1, m2)
# or row-based colors for gradient patterns
COLOR_PATTERNS = {
    # Pride: each row is a different rainbow color
    "pride": {
        "type": "per_row",
        "colors": ["red", "orange", "yellow", "green", "blue", "violet"],
    },
    # Rainbow: each digit is a different rainbow color
    "rainbow": {
        "type": "per_digit",
        "colors": ["red", "orange", "yellow", "green", "blue", "violet"],
    },
    # Sunset: warm gradient from top to bottom
    "sunset": {
        "type": "per_row",
        "colors": ["red", "red", "orange", "orange", "yellow", "yellow"],
    },
    # Ocean: cool gradient from top to bottom
    "ocean": {
        "type": "per_row",
        "colors": ["blue", "blue", "green", "green", "violet", "violet"],
    },
    # Retro: classic amber LED look
    "retro": {
        "type": "per_row",
        "colors": ["orange", "orange", "yellow", "yellow", "orange", "orange"],
    },
    # Christmas: alternating red and green
    "christmas": {
        "type": "per_digit",
        "colors": ["red", "green", "red", "green", "red", "green"],
    },
    # Halloween: alternating orange and violet
    "halloween": {
        "type": "per_digit",
        "colors": ["orange", "violet", "orange", "violet", "orange", "violet"],
    },
}

# Digit patterns (6 rows x 4 columns each) - full board height
# 1 = foreground (digit color), 0 = background
# All digits designed with consistent visual weight (2-col minimum strokes)
DIGIT_PATTERNS = {
    0: [
        [1, 1, 1, 1],
        [1, 0, 0, 1],
        [1, 0, 0, 1],
        [1, 0, 0, 1],
        [1, 0, 0, 1],
        [1, 1, 1, 1],
    ],
    1: [
        [0, 1, 1, 0],
        [1, 1, 1, 0],
        [0, 1, 1, 0],
        [0, 1, 1, 0],
        [0, 1, 1, 0],
        [1, 1, 1, 1],
    ],
    2: [
        [1, 1, 1, 1],
        [0, 0, 1, 1],
        [0, 0, 1, 1],
        [1, 1, 1, 1],
        [1, 1, 0, 0],
        [1, 1, 1, 1],
    ],
    3: [
        [1, 1, 1, 1],
        [0, 0, 1, 1],
        [1, 1, 1, 1],
        [0, 0, 1, 1],
        [0, 0, 1, 1],
        [1, 1, 1, 1],
    ],
    4: [
        [1, 0, 0, 1],
        [1, 0, 0, 1],
        [1, 0, 0, 1],
        [1, 1, 1, 1],
        [0, 0, 1, 1],
        [0, 0, 1, 1],
    ],
    5: [
        [1, 1, 1, 1],
        [1, 1, 0, 0],
        [1, 1, 1, 1],
        [0, 0, 1, 1],
        [0, 0, 1, 1],
        [1, 1, 1, 1],
    ],
    6: [
        [1, 1, 1, 1],
        [1, 1, 0, 0],
        [1, 1, 1, 1],
        [1, 1, 0, 1],
        [1, 0, 0, 1],
        [1, 1, 1, 1],
    ],
    7: [
        [1, 1, 1, 1],
        [0, 0, 1, 1],
        [0, 0, 1, 1],
        [0, 0, 1, 1],
        [0, 0, 1, 1],
        [0, 0, 1, 1],
    ],
    8: [
        [1, 1, 1, 1],
        [1, 0, 0, 1],
        [1, 1, 1, 1],
        [1, 1, 1, 1],
        [1, 0, 0, 1],
        [1, 1, 1, 1],
    ],
    9: [
        [1, 1, 1, 1],
        [1, 0, 0, 1],
        [1, 1, 1, 1],
        [0, 0, 1, 1],
        [0, 0, 1, 1],
        [1, 1, 1, 1],
    ],
}

# Colon pattern (6 rows x 2 columns) - full board height
# Dots at rows 1-2 and 4-5 for visibility
COLON_PATTERN = [
    [0, 0],
    [1, 1],
    [0, 0],
    [0, 0],
    [1, 1],
    [0, 0],
]


class VisualClockPlugin(PluginBase):
    """Visual clock plugin.
    
    Displays a full-screen clock with large pixel-art style digits.
    """
    
    @property
    def plugin_id(self) -> str:
        return "visual_clock"
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate visual clock configuration."""
        errors = []
        
        # Validate timezone
        timezone = config.get("timezone", "America/Los_Angeles")
        try:
            pytz.timezone(timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            errors.append(f"Invalid timezone: {timezone}")
        
        # Validate time format
        time_format = config.get("time_format", "12h")
        if time_format not in ["12h", "24h"]:
            errors.append(f"Invalid time format: {time_format}. Must be '12h' or '24h'.")
        
        # Validate color pattern
        color_pattern = config.get("color_pattern", "solid")
        valid_patterns = ["solid"] + list(COLOR_PATTERNS.keys())
        if color_pattern not in valid_patterns:
            errors.append(f"Invalid color pattern: {color_pattern}")
        
        # Validate colors
        digit_color = config.get("digit_color", "white")
        if digit_color not in COLOR_MAP:
            errors.append(f"Invalid digit color: {digit_color}")
        
        background_color = config.get("background_color", "black")
        if background_color not in COLOR_MAP:
            errors.append(f"Invalid background color: {background_color}")
        
        return errors
    
    def fetch_data(self) -> PluginResult:
        """Fetch current time and generate visual clock display."""
        try:
            # Get configuration
            timezone_str = self.config.get("timezone", "America/Los_Angeles")
            time_format = self.config.get("time_format", "12h")
            color_pattern = self.config.get("color_pattern", "solid")
            digit_color = self.config.get("digit_color", "white")
            background_color = self.config.get("background_color", "black")
            
            # Get current time in configured timezone
            tz = pytz.timezone(timezone_str)
            now = datetime.now(tz)
            
            # Format time based on setting
            if time_format == "12h":
                hour = now.hour % 12
                if hour == 0:
                    hour = 12
                time_str = now.strftime("%I:%M %p").lstrip("0")
            else:
                hour = now.hour
                time_str = now.strftime("%H:%M")
            
            minute = now.minute
            
            # Generate the visual clock array
            clock_array = self._generate_clock_display(
                hour, minute, color_pattern, digit_color, background_color
            )
            
            # Convert array to string format
            clock_string = self._array_to_string(clock_array)
            
            data = {
                "visual_clock": clock_string,
                "visual_clock_array": clock_array,
                "time": time_str,
                "time_format": time_format,
                "hour": str(hour),
                "minute": str(minute).zfill(2),
            }
            
            return PluginResult(
                available=True,
                data=data
            )
            
        except Exception as e:
            logger.exception("Error fetching visual clock data")
            return PluginResult(
                available=False,
                error=str(e)
            )
    
    def _generate_clock_display(
        self,
        hour: int,
        minute: int,
        color_pattern: str,
        digit_color: str,
        background_color: str
    ) -> List[List[int]]:
        """Generate the 6x22 clock display array.
        
        Layout: [H1][gap][H2][gap][:][gap][M1][gap][M2]
        - Each digit is 4 columns wide
        - Colon is 2 columns wide
        - 1-column gaps on both sides of colon
        
        Total: 4 + 1 + 4 + 1 + 2 + 1 + 4 + 1 + 4 = 22 columns
        
        Args:
            hour: Hour value (1-12 for 12h, 0-23 for 24h)
            minute: Minute value (0-59)
            color_pattern: Color pattern name ("solid", "pride", etc.)
            digit_color: Color name for solid pattern
            background_color: Color name for background
            
        Returns:
            6x22 array of character codes
        """
        bg = COLOR_MAP.get(background_color, BoardChars.BLACK)
        
        # Initialize the board with background color
        board = [[bg for _ in range(COLS)] for _ in range(ROWS)]
        
        # Parse hour and minute into individual digits
        h1 = hour // 10
        h2 = hour % 10
        m1 = minute // 10
        m2 = minute % 10
        
        # Calculate starting positions
        # Layout: [4][1][4][1][2][1][4][1][4] = 22 (gaps on both sides of colon)
        col_positions = {
            "h1": 0,      # First hour digit starts at column 0
            "h2": 5,      # Second hour digit starts at column 5 (0+4+1)
            "colon": 10,  # Colon starts at column 10 (5+4+1)
            "m1": 13,     # First minute digit starts at column 13 (10+2+1)
            "m2": 18,     # Second minute digit starts at column 18 (13+4+1)
        }
        
        # Row offset (start at row 0 to use full board height)
        row_offset = 0
        
        # Get colors based on pattern
        if color_pattern == "solid" or color_pattern not in COLOR_PATTERNS:
            # Solid color for all elements
            fg = COLOR_MAP.get(digit_color, BoardChars.WHITE)
            colors_h1 = colors_h2 = colors_colon = colors_m1 = colors_m2 = [fg] * ROWS
        else:
            pattern = COLOR_PATTERNS[color_pattern]
            if pattern["type"] == "per_row":
                # Same row colors for all elements
                row_colors = [COLOR_MAP[c] for c in pattern["colors"]]
                colors_h1 = colors_h2 = colors_colon = colors_m1 = colors_m2 = row_colors
            else:  # per_digit
                # Different color per digit element
                pattern_colors = pattern["colors"]
                colors_h1 = [COLOR_MAP[pattern_colors[0]]] * ROWS
                colors_h2 = [COLOR_MAP[pattern_colors[1]]] * ROWS
                colors_colon = [COLOR_MAP[pattern_colors[2]]] * ROWS
                colors_m1 = [COLOR_MAP[pattern_colors[3]]] * ROWS
                colors_m2 = [COLOR_MAP[pattern_colors[4 % len(pattern_colors)]]] * ROWS
        
        # Draw hour digit 1 (only if not zero)
        if h1 > 0:
            self._draw_digit_colored(board, h1, row_offset, col_positions["h1"], colors_h1, bg)
        
        # Draw hour digit 2
        self._draw_digit_colored(board, h2, row_offset, col_positions["h2"], colors_h2, bg)
        
        # Draw colon
        self._draw_colon_colored(board, row_offset, col_positions["colon"], colors_colon, bg)
        
        # Draw minute digit 1
        self._draw_digit_colored(board, m1, row_offset, col_positions["m1"], colors_m1, bg)
        
        # Draw minute digit 2
        self._draw_digit_colored(board, m2, row_offset, col_positions["m2"], colors_m2, bg)
        
        return board
    
    def _draw_digit(
        self,
        board: List[List[int]],
        digit: int,
        row_start: int,
        col_start: int,
        fg: int,
        bg: int
    ) -> None:
        """Draw a digit pattern onto the board.
        
        Args:
            board: The 6x22 board array to modify
            digit: Digit value (0-9)
            row_start: Starting row position
            col_start: Starting column position
            fg: Foreground color code
            bg: Background color code
        """
        pattern = DIGIT_PATTERNS[digit]
        for row_idx, row in enumerate(pattern):
            for col_idx, val in enumerate(row):
                board_row = row_start + row_idx
                board_col = col_start + col_idx
                if 0 <= board_row < ROWS and 0 <= board_col < COLS:
                    board[board_row][board_col] = fg if val == 1 else bg
    
    def _draw_colon(
        self,
        board: List[List[int]],
        row_start: int,
        col_start: int,
        fg: int,
        bg: int
    ) -> None:
        """Draw a colon pattern onto the board.
        
        Args:
            board: The 6x22 board array to modify
            row_start: Starting row position
            col_start: Starting column position
            fg: Foreground color code
            bg: Background color code
        """
        for row_idx, row in enumerate(COLON_PATTERN):
            for col_idx, val in enumerate(row):
                board_row = row_start + row_idx
                board_col = col_start + col_idx
                if 0 <= board_row < ROWS and 0 <= board_col < COLS:
                    board[board_row][board_col] = fg if val == 1 else bg
    
    def _draw_digit_colored(
        self,
        board: List[List[int]],
        digit: int,
        row_start: int,
        col_start: int,
        row_colors: List[int],
        bg: int
    ) -> None:
        """Draw a digit pattern with per-row colors.
        
        Args:
            board: The 6x22 board array to modify
            digit: Digit value (0-9)
            row_start: Starting row position
            col_start: Starting column position
            row_colors: List of color codes, one per row
            bg: Background color code
        """
        pattern = DIGIT_PATTERNS[digit]
        for row_idx, row in enumerate(pattern):
            fg = row_colors[row_idx] if row_idx < len(row_colors) else row_colors[-1]
            for col_idx, val in enumerate(row):
                board_row = row_start + row_idx
                board_col = col_start + col_idx
                if 0 <= board_row < ROWS and 0 <= board_col < COLS:
                    board[board_row][board_col] = fg if val == 1 else bg
    
    def _draw_colon_colored(
        self,
        board: List[List[int]],
        row_start: int,
        col_start: int,
        row_colors: List[int],
        bg: int
    ) -> None:
        """Draw a colon pattern with per-row colors.
        
        Args:
            board: The 6x22 board array to modify
            row_start: Starting row position
            col_start: Starting column position
            row_colors: List of color codes, one per row
            bg: Background color code
        """
        for row_idx, row in enumerate(COLON_PATTERN):
            fg = row_colors[row_idx] if row_idx < len(row_colors) else row_colors[-1]
            for col_idx, val in enumerate(row):
                board_row = row_start + row_idx
                board_col = col_start + col_idx
                if 0 <= board_row < ROWS and 0 <= board_col < COLS:
                    board[board_row][board_col] = fg if val == 1 else bg
    
    def _array_to_string(self, array: List[List[int]]) -> str:
        """Convert board array to string format with color markers.
        
        Args:
            array: 6x22 array of character codes
            
        Returns:
            Newline-separated string with color markers
        """
        color_markers = {
            BoardChars.RED: "{red}",
            BoardChars.ORANGE: "{orange}",
            BoardChars.YELLOW: "{yellow}",
            BoardChars.GREEN: "{green}",
            BoardChars.BLUE: "{blue}",
            BoardChars.VIOLET: "{violet}",
            BoardChars.WHITE: "{white}",
            BoardChars.BLACK: "{black}",
        }
        
        lines = []
        for row in array:
            line = ""
            for code in row:
                if code in color_markers:
                    line += color_markers[code]
                else:
                    line += " "
            lines.append(line)
        
        return "\n".join(lines)


# Export the plugin class
Plugin = VisualClockPlugin
