"""White Noise plugin for FiestaBoard.

Generates a gentle rain / white noise visual effect on the 6x22 board.
Only a few white tiles appear at a time, drifting slowly downward like
light rain, so the physical board produces a soft, soothing pitter-patter
rather than an overwhelming clatter.
"""

import random
from typing import Any, Dict, List

import logging

from src.plugins.base import PluginBase, PluginResult
from src.board_chars import BoardChars

logger = logging.getLogger(__name__)

# Board dimensions
ROWS = 6
COLS = 22

# Intensity presets: how many drops appear per frame
INTENSITY_PRESETS = {
    "light": {"drops": 3, "description": "Light drizzle — very few tiles"},
    "medium": {"drops": 6, "description": "Gentle rain — a handful of tiles"},
    "heavy": {"drops": 10, "description": "Steady rain — more tiles"},
    "custom": {"drops": 0, "description": "Custom drop count (use drops_per_frame)"},
}

DEFAULT_INTENSITY = "light"
DEFAULT_DROPS_PER_FRAME = 3
DEFAULT_MAX_DROPS = 30

# Color palette for rain drops
RAINDROP_COLORS = {
    "white": BoardChars.WHITE,
    "blue": BoardChars.BLUE,
    "violet": BoardChars.VIOLET,
}

DEFAULT_DROP_COLOR = "white"


class WhiteNoisePlugin(PluginBase):
    """White noise / rain ambiance plugin.

    Creates a gentle, slowly-cascading rain effect on the board.  Each call
    to ``fetch_data`` produces a new frame where a small number of "raindrop"
    tiles appear at random positions.  The effect is designed to be subtle —
    only a few tiles change between refreshes — so the physical board makes
    a quiet, soothing pitter-patter sound.
    """

    def __init__(self, manifest: Dict[str, Any]):
        """Initialize the white noise plugin."""
        super().__init__(manifest)
        # Persistent rain state: list of (row, col) for active drops
        self._drops: List[List[int]] = []

    @property
    def plugin_id(self) -> str:
        return "white_noise"

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate white noise configuration."""
        errors = []

        intensity = config.get("intensity", DEFAULT_INTENSITY)
        if intensity not in INTENSITY_PRESETS:
            errors.append(
                f"Invalid intensity '{intensity}'. "
                f"Must be one of: {', '.join(INTENSITY_PRESETS.keys())}"
            )

        drop_color = config.get("drop_color", DEFAULT_DROP_COLOR)
        if drop_color not in RAINDROP_COLORS:
            errors.append(
                f"Invalid drop_color '{drop_color}'. "
                f"Must be one of: {', '.join(RAINDROP_COLORS.keys())}"
            )

        # Validate custom drop count
        if intensity == "custom":
            drops_per_frame = config.get("drops_per_frame", DEFAULT_DROPS_PER_FRAME)
            if not isinstance(drops_per_frame, int) or drops_per_frame < 1:
                errors.append("drops_per_frame must be a positive integer")
            elif drops_per_frame > 22:
                errors.append("drops_per_frame cannot exceed 22 (board width)")

        # Validate max drops
        max_drops = config.get("max_drops", DEFAULT_MAX_DROPS)
        if not isinstance(max_drops, int) or max_drops < 1:
            errors.append("max_drops must be a positive integer")
        elif max_drops > ROWS * COLS:
            errors.append(f"max_drops cannot exceed {ROWS * COLS} (total board tiles)")

        return errors

    # --------------------------------------------------------------------- #
    # Data fetch (the main entry-point)
    # --------------------------------------------------------------------- #

    def fetch_data(self) -> PluginResult:
        """Generate the next rain frame."""
        try:
            intensity = self.config.get("intensity", DEFAULT_INTENSITY)
            drop_color_name = self.config.get("drop_color", DEFAULT_DROP_COLOR)
            drop_color = RAINDROP_COLORS.get(drop_color_name, BoardChars.WHITE)
            
            # Determine number of drops to spawn
            if intensity == "custom":
                num_drops = self.config.get("drops_per_frame", DEFAULT_DROPS_PER_FRAME)
            else:
                num_drops = INTENSITY_PRESETS.get(
                    intensity, INTENSITY_PRESETS[DEFAULT_INTENSITY]
                )["drops"]
            
            # Get max drops limit
            max_drops = self.config.get("max_drops", DEFAULT_MAX_DROPS)

            # Advance the simulation one step
            board = self._step(num_drops, drop_color, max_drops)

            # Convert to the string representation used by the display engine
            board_string = self._board_to_string(board)

            data = {
                "white_noise": board_string,
                "white_noise_array": board,
                "intensity": intensity,
                "drop_color": drop_color_name,
                "active_drops": len(self._drops),
                "drops_per_frame": num_drops,
                "max_drops": max_drops,
            }

            return PluginResult(available=True, data=data)

        except Exception as e:
            logger.exception("Error generating white noise frame")
            return PluginResult(available=False, error=str(e))

    # --------------------------------------------------------------------- #
    # Simulation helpers
    # --------------------------------------------------------------------- #

    def _step(self, num_new_drops: int, color: int, max_drops: int) -> List[List[int]]:
        """Advance the rain simulation by one tick.

        1. Move every existing drop down by one row.
        2. Remove drops that have fallen off the bottom.
        3. Spawn ``num_new_drops`` new drops at the top row.
        4. Render the board.

        Args:
            num_new_drops: How many new drops to create at the top.
            color: Board character code for the raindrop tile.
            max_drops: Maximum number of drops allowed on board simultaneously.

        Returns:
            6×22 board array of character codes.
        """
        # 1. Advance existing drops downward
        self._drops = [[r + 1, c] for r, c in self._drops if r + 1 < ROWS]

        # 2. Enforce max drops limit
        if len(self._drops) > max_drops:
            self._drops = self._drops[:max_drops]

        # 3. Spawn new drops along the top row at random columns
        occupied_cols = {c for _, c in self._drops if _ == 0}
        available_cols = [c for c in range(COLS) if c not in occupied_cols]
        if available_cols and len(self._drops) < max_drops:
            # Don't spawn more than would exceed max_drops
            spawn_count = min(num_new_drops, len(available_cols), max_drops - len(self._drops))
            new_cols = random.sample(available_cols, spawn_count)
            for c in new_cols:
                self._drops.append([0, c])

        # 4. Render board
        board = self._render(color)
        return board

    def _render(self, color: int) -> List[List[int]]:
        """Render the current drop positions onto a blank board.

        Args:
            color: Board character code for the raindrop tile.

        Returns:
            6×22 board array of character codes.
        """
        board = [[BoardChars.BLACK] * COLS for _ in range(ROWS)]
        for r, c in self._drops:
            if 0 <= r < ROWS and 0 <= c < COLS:
                board[r][c] = color
        return board

    def _board_to_string(self, board: List[List[int]]) -> str:
        """Convert board array to the color-marker string format.

        Args:
            board: 6×22 array of character codes.

        Returns:
            Newline-separated string using ``{color}`` markers.
        """
        color_map = {
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
        for row in board:
            line = ""
            for code in row:
                if code in color_map:
                    line += color_map[code]
                else:
                    line += " "
            lines.append(line)
        return "\n".join(lines)

    def cleanup(self) -> None:
        """Reset rain state when the plugin is disabled."""
        self._drops = []


# Export the plugin class
Plugin = WhiteNoisePlugin
