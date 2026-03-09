"""Star Trek Quotes plugin for FiestaBoard.

Displays random Star Trek quotes from TNG, Voyager, and DS9.
"""

from typing import Any, Dict, List, Optional
import logging
import json
import random
from pathlib import Path

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)


class StarTrekQuotesPlugin(PluginBase):
    """Star Trek quotes plugin.
    
    Provides random quotes from TNG, Voyager, and DS9 with
    configurable series weighting.
    """
    
    # Series color mapping
    SERIES_COLORS = {
        "tng": "{67}",     # Blue
        "voyager": "{64}", # Orange
        "ds9": "{68}",     # Violet
    }
    
    def __init__(self, manifest: Dict[str, Any]):
        """Initialize the Star Trek quotes plugin."""
        super().__init__(manifest)
        self._quotes: Dict[str, List[Dict]] = {}
        self._load_quotes()
    
    @property
    def plugin_id(self) -> str:
        return "star_trek_quotes"
    
    def _load_quotes(self) -> None:
        """Load quotes from JSON file."""
        try:
            # Try loading from plugin directory first
            plugin_dir = Path(__file__).parent
            quotes_file = plugin_dir / "quotes.json"
            
            if not quotes_file.exists():
                # Fall back to legacy location
                legacy_file = Path(__file__).parent.parent.parent / "src" / "utils" / "star_trek_quotes.json"
                if legacy_file.exists():
                    quotes_file = legacy_file
                else:
                    logger.warning("Star Trek quotes file not found")
                    self._quotes = {"tng": [], "voyager": [], "ds9": []}
                    return
            
            with open(quotes_file, 'r') as f:
                self._quotes = json.load(f)
            
            logger.info(
                f"Loaded Star Trek quotes: TNG={len(self._quotes.get('tng', []))}, "
                f"Voyager={len(self._quotes.get('voyager', []))}, "
                f"DS9={len(self._quotes.get('ds9', []))}"
            )
        except Exception as e:
            logger.error(f"Error loading Star Trek quotes: {e}")
            self._quotes = {"tng": [], "voyager": [], "ds9": []}
    
    def _parse_ratio(self) -> tuple:
        """Parse the series ratio from config."""
        ratio_str = self.config.get("ratio", "3:5:9")
        try:
            parts = ratio_str.split(":")
            if len(parts) == 3:
                return int(parts[0]), int(parts[1]), int(parts[2])
        except (ValueError, AttributeError):
            pass
        return 3, 5, 9
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate star trek quotes configuration."""
        errors = []
        
        ratio = config.get("ratio", "3:5:9")
        if ratio:
            parts = ratio.split(":")
            if len(parts) != 3:
                errors.append("Ratio must be in format N:N:N (e.g., 3:5:9)")
            else:
                for part in parts:
                    try:
                        int(part)
                    except ValueError:
                        errors.append("Ratio parts must be integers")
                        break
        
        return errors
    
    def fetch_data(self) -> PluginResult:
        """Fetch a random Star Trek quote."""
        if not self._quotes:
            self._load_quotes()
        
        if not any(self._quotes.values()):
            return PluginResult(
                available=False,
                error="No quotes available"
            )
        
        try:
            tng_weight, voyager_weight, ds9_weight = self._parse_ratio()
            
            # Create weighted pool
            series_pool = (
                ['tng'] * tng_weight +
                ['voyager'] * voyager_weight +
                ['ds9'] * ds9_weight
            )
            
            # Select random series
            selected_series = random.choice(series_pool)
            series_quotes = self._quotes.get(selected_series, [])
            
            if not series_quotes:
                # Fallback to any available series
                all_quotes = []
                for series, quotes_list in self._quotes.items():
                    all_quotes.extend([{**q, 'series': series} for q in quotes_list])
                if not all_quotes:
                    return PluginResult(
                        available=False,
                        error="No quotes available"
                    )
                quote_data = random.choice(all_quotes)
            else:
                quote_data = random.choice(series_quotes)
                quote_data = {**quote_data, 'series': selected_series}
            
            data = {
                "quote": quote_data.get("quote", ""),
                "character": quote_data.get("character", "Unknown"),
                "series": quote_data.get("series", "").upper(),
                "series_color": self.SERIES_COLORS.get(quote_data.get("series", ""), ""),
            }
            
            return PluginResult(
                available=True,
                data=data
            )
            
        except Exception as e:
            logger.exception("Error fetching Star Trek quote")
            return PluginResult(
                available=False,
                error=str(e)
            )
    
    def get_formatted_display(self) -> Optional[List[str]]:
        """Return default formatted quote display."""
        result = self.fetch_data()
        if not result.available or not result.data:
            return None
        
        data = result.data
        quote = data["quote"]
        character = data["character"]
        
        # Word wrap quote to fit
        lines = [""]  # Start with empty line
        words = quote.split()
        current_line = ""
        
        for word in words:
            if len(current_line) + len(word) + 1 <= 22:
                current_line = f"{current_line} {word}".strip()
            else:
                if len(lines) < 5:
                    lines.append(current_line)
                    current_line = word
                else:
                    break
        
        if current_line and len(lines) < 5:
            lines.append(current_line)
        
        # Pad to 5 lines (leaving room for character)
        while len(lines) < 5:
            lines.append("")
        
        # Add character attribution
        lines.append(f"- {character}"[:22].rjust(22))
        
        return lines[:6]


# Export the plugin class
Plugin = StarTrekQuotesPlugin

