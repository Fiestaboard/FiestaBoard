"""White Noise plugin for FiestaBoard.

Generates a gentle rain / white noise visual effect on the 6x22 board.
Only a few white tiles appear at a time, drifting slowly downward like
light rain, so the physical board produces a soft, soothing pitter-patter
rather than an overwhelming clatter.
"""

import random
from typing import Any, Dict, List, Optional

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
}

DEFAULT_INTENSITY = "light"

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
        """Initialise the white noise plugin."""
        super().__init__(manifest)
        # Persistent rain state: list of (row, col) for active drops
        self._drops: List[List[int]] = []

    @property
    def plugin_id(self) -> str:
        """Return plugin identifier."""
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
            num_drops = INTENSITY_PRESETS.get(
                intensity, INTENSITY_PRESETS[DEFAULT_INTENSITY]
            )["drops"]

            # Advance the simulation one step
            board = self._step(num_drops, drop_color)

            # Convert to the string representation used by the display engine
            board_string = self._board_to_string(board)

            data = {
                "white_noise": board_string,
                "white_noise_array": board,
                "intensity": intensity,
                "drop_color": drop_color_name,
                "active_drops": len(self._drops),
            }

            return PluginResult(available=True, data=data)

        except Exception as e:
            logger.exception("Error generating white noise frame")
            return PluginResult(available=False, error=str(e))

    # --------------------------------------------------------------------- #
    # Simulation helpers
    # --------------------------------------------------------------------- #

    def _step(self, num_new_drops: int, color: int) -> List[List[int]]:
        """Advance the rain simulation by one tick.

        1. Move every existing drop down by one row.
        2. Remove drops that have fallen off the bottom.
        3. Spawn ``num_new_drops`` new drops at the top row.
        4. Render the board.

        Args:
            num_new_drops: How many new drops to create at the top.
            color: Board character code for the raindrop tile.

        Returns:
            6×22 board array of character codes.
        """
        # 1. Advance existing drops downward
        self._drops = [[r + 1, c] for r, c in self._drops if r + 1 < ROWS]

        # 2. Spawn new drops along the top row at random columns
        occupied_cols = {c for _, c in self._drops if _ == 0}
        available_cols = [c for c in range(COLS) if c not in occupied_cols]
        if available_cols:
            spawn_count = min(num_new_drops, len(available_cols))
            new_cols = random.sample(available_cols, spawn_count)
            for c in new_cols:
                self._drops.append([0, c])

        # 3. Render board
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
        """Convert board array to the colour-marker string format.

        Args:
            board: 6×22 array of character codes.

        Returns:
            Newline-separated string using ``{colour}`` markers.
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
