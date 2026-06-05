"""Random plugin for FiestaBoard.

Provides randomly selected values as template variables, refreshed on a
configurable interval.
"""

import logging
from random import choice as _random_choice
from typing import Any

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

BOARD_COLORS = ["red", "orange", "yellow", "green", "blue", "violet"]

# Maps color names to board character codes; used to produce color tiles.
# White (69) and black (70) are excluded: they render inverted on white boards,
# making color_name misleading (a "black" tile appears white on a white board).
_COLOR_TILE_CODES = {"red": 63, "orange": 64, "yellow": 65, "green": 66, "blue": 67, "violet": 68}

_DEFAULT_CHOICES = ["Heads", "Tails"]


class RandomPlugin(PluginBase):
    """Exposes randomly selected values as template variables."""

    @property
    def plugin_id(self) -> str:
        return "random"

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = self._validate_refresh_seconds(config)
        choices = config.get("choices", _DEFAULT_CHOICES)
        if not isinstance(choices, list):
            errors.append("choices must be a list of strings")
        elif len(choices) < 2:
            errors.append("choices must have at least 2 items")
        elif len(choices) > 10:
            errors.append("choices must have at most 10 items")
        else:
            for i, item in enumerate(choices):
                if not isinstance(item, str) or not item.strip():
                    errors.append(f"choices[{i}] must be a non-empty string")
        return errors

    def fetch_data(self) -> PluginResult:
        try:
            choices = self.config.get("choices", _DEFAULT_CHOICES)
            if not isinstance(choices, list) or len(choices) < 2:
                choices = _DEFAULT_CHOICES

            color = _random_choice(BOARD_COLORS)
            data = {
                "choice": _random_choice(choices),
                "coin_flip": _random_choice(["Heads", "Tails"]),
                "color": f"{{{_COLOR_TILE_CODES[color]}}}",
                "color_name": color,
            }

            return PluginResult(available=True, data=data)

        except Exception as e:
            logger.exception("Error generating random data")
            return PluginResult(available=False, error=str(e))


Plugin = RandomPlugin
