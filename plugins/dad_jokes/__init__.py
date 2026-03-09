"""Dad Jokes plugin for FiestaBoard.

Displays random dad jokes from the icanhazdadjoke API.
"""

from typing import List, Optional
import logging
import requests

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

API_URL = "https://icanhazdadjoke.com/"
USER_AGENT = "FiestaBoard (https://github.com/FiestaBoard/FiestaBoard)"


class DadJokesPlugin(PluginBase):
    """Dad Jokes plugin.

    Fetches random dad jokes from the icanhazdadjoke API
    and displays them on the board.
    """

    @property
    def plugin_id(self) -> str:
        return "dad_jokes"

    def fetch_data(self) -> PluginResult:
        """Fetch a random dad joke from the icanhazdadjoke API."""
        try:
            response = requests.get(
                API_URL,
                headers={
                    "Accept": "application/json",
                    "User-Agent": USER_AGENT,
                },
                timeout=10,
            )
            response.raise_for_status()

            joke_data = response.json()
            joke_text = joke_data.get("joke", "")

            if not joke_text:
                return PluginResult(
                    available=False,
                    error="No joke returned from API",
                )

            return PluginResult(
                available=True,
                data={"joke": joke_text},
            )

        except Exception as e:
            logger.exception("Error fetching dad joke")
            return PluginResult(
                available=False,
                error=str(e),
            )

    def get_formatted_display(self) -> Optional[List[str]]:
        """Return default formatted joke display."""
        result = self.get_data()
        if not result.available or not result.data:
            return None

        joke = result.data["joke"]

        # Word wrap joke to fit 22-char lines
        lines = []
        words = joke.split()
        current_line = ""

        for word in words:
            if len(current_line) + len(word) + 1 <= 22:
                current_line = f"{current_line} {word}".strip()
            else:
                if len(lines) < 6:
                    lines.append(current_line)
                    current_line = word
                else:
                    break

        if current_line and len(lines) < 6:
            lines.append(current_line)

        # Pad to 6 lines
        while len(lines) < 6:
            lines.append("")

        return lines[:6]


# Export the plugin class
Plugin = DadJokesPlugin
