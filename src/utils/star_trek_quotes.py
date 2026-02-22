"""
Star Trek Quotes Data Source

Provides random Star Trek quotes from TNG, Voyager, and DS9
with a configurable ratio between series.
"""

import json
import random
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class StarTrekQuotesSource:
    """Source for Star Trek quotes."""
    
    def __init__(self, tng_weight: int = 3, voyager_weight: int = 5, ds9_weight: int = 9):
        """
        Initialize Star Trek quotes source.
        
        Args:
            tng_weight: Weight for TNG quotes (default: 3)
            voyager_weight: Weight for Voyager quotes (default: 5)
            ds9_weight: Weight for DS9 quotes (default: 9)
        """
        self.tng_weight = tng_weight
        self.voyager_weight = voyager_weight
        self.ds9_weight = ds9_weight
        self.quotes = self._load_quotes()
        logger.info(f"Loaded Star Trek quotes: TNG={len(self.quotes.get('tng', []))}, "
                   f"Voyager={len(self.quotes.get('voyager', []))}, "
                   f"DS9={len(self.quotes.get('ds9', []))}")
    
    def _load_quotes(self) -> Dict:
        """Load quotes from JSON file."""
        try:
            quotes_file = Path(__file__).parent / "star_trek_quotes.json"
            with open(quotes_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading Star Trek quotes: {e}")
            return {"tng": [], "voyager": [], "ds9": []}
    
    def get_random_quote(self) -> Optional[Dict]:
        """
        Get a random quote respecting the series ratio.
        
        Returns:
            Dictionary with 'quote', 'character', and 'series' keys
        """
        if not self.quotes:
            return None
        
        # Create weighted list of series
        series_pool = (
            ['tng'] * self.tng_weight +
            ['voyager'] * self.voyager_weight +
            ['ds9'] * self.ds9_weight
        )
        
        # Select random series based on weights
        selected_series = random.choice(series_pool)
        
        # Get quotes from selected series
        series_quotes = self.quotes.get(selected_series, [])
        if not series_quotes:
            # Fallback to any available series
            all_quotes = []
            for series, quotes_list in self.quotes.items():
                all_quotes.extend([{**q, 'series': series} for q in quotes_list])
            if not all_quotes:
                return None
            quote_data = random.choice(all_quotes)
        else:
            quote_data = random.choice(series_quotes)
            quote_data = {**quote_data, 'series': selected_series}
        
        logger.debug(f"Selected quote from {selected_series}: {quote_data['quote'][:30]}...")
        return quote_data


def get_star_trek_quotes_source() -> Optional[StarTrekQuotesSource]:
    """
    Factory function to create Star Trek quotes source.
    
    Returns:
        StarTrekQuotesSource instance or None if disabled
    """
    from ..config import Config
    
    if not Config.STAR_TREK_QUOTES_ENABLED:
        return None
    
    try:
        # Parse ratio from config
        ratio_parts = Config.STAR_TREK_QUOTES_RATIO.split(':')
        if len(ratio_parts) == 3:
            tng_weight = int(ratio_parts[0])
            voyager_weight = int(ratio_parts[1])
            ds9_weight = int(ratio_parts[2])
        else:
            # Default ratio
            tng_weight, voyager_weight, ds9_weight = 3, 5, 9
        
        return StarTrekQuotesSource(tng_weight, voyager_weight, ds9_weight)
    except Exception as e:
        logger.error(f"Error creating Star Trek quotes source: {e}")
        return None

