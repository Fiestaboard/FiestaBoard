"""Random plugin for FiestaBoard.

Provides randomly selected values as template variables, refreshed on a
configurable interval.
"""

import random as _random
from typing import Any, Dict, List, Optional
import logging

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

BOARD_COLORS = ["red", "orange", "yellow", "green", "blue", "violet", "white", "black"]

_DEFAULT_CHOICES = ["Heads", "Tails"]


class RandomPlugin(PluginBase):
    """Exposes randomly selected values as template variables."""

    @property
    def plugin_id(self) -> str:
        return "random"

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
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

            data = {
                "choice": _random.choice(choices),
                "coin_flip": _random.choice(["Heads", "Tails"]),
                "color": _random.choice(BOARD_COLORS),
            }

            return PluginResult(available=True, data=data)

        except Exception as e:
            logger.exception("Error generating random data")
            return PluginResult(available=False, error=str(e))


Plugin = RandomPlugin
