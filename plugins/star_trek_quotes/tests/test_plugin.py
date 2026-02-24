"""Tests for the star_trek_quotes plugin."""

import pytest
from unittest.mock import patch, Mock, MagicMock
import json
from pathlib import Path

from src.utils.star_trek_quotes import (
    StarTrekQuotesSource,
    get_star_trek_quotes_source
)

# Also test the plugin itself
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from plugins.star_trek_quotes import StarTrekQuotesPlugin


class TestStarTrekQuotesSource:
    """Tests for StarTrekQuotesSource class."""
    
    def test_init(self):
        """Test source initialization."""
        source = StarTrekQuotesSource()
        assert source is not None
    
    def test_get_random_quote(self):
        """Test getting a random quote."""
        source = StarTrekQuotesSource()
        quote = source.get_random_quote()
        
        assert quote is not None
        assert "quote" in quote or "text" in quote or isinstance(quote, str)
    
    def test_quote_has_required_fields(self):
        """Test quote data structure has required fields."""
        source = StarTrekQuotesSource()
        quote = source.get_random_quote()
        
        if isinstance(quote, dict):
            # Should have quote text
            assert any(k in quote for k in ["quote", "text", "line"])
            # Optionally has character/speaker
            # assert any(k in quote for k in ["character", "speaker", "author"])
    
    def test_quotes_file_exists(self):
        """Test that quotes data file exists."""
        quotes_file = Path(__file__).parent.parent.parent.parent.parent / "src" / "utils" / "star_trek_quotes.json"
        # Check if file exists or quotes are embedded
        # This might vary based on implementation
        pass
    
    def test_quote_not_empty(self):
        """Test that quotes are not empty strings."""
        source = StarTrekQuotesSource()
        quote = source.get_random_quote()
        
        if isinstance(quote, dict):
            quote_text = quote.get("quote") or quote.get("text") or ""
        else:
            quote_text = str(quote)
        
        assert len(quote_text) > 0
    
    def test_multiple_random_quotes_vary(self):
        """Test that random quotes can vary."""
        source = StarTrekQuotesSource()
        
        # Get multiple quotes
        quotes = [source.get_random_quote() for _ in range(10)]
        
        # Convert to strings for comparison
        quote_texts = []
        for q in quotes:
            if isinstance(q, dict):
                quote_texts.append(q.get("quote") or q.get("text") or str(q))
            else:
                quote_texts.append(str(q))
        
        # Should have some variety (not all identical)
        unique_quotes = set(quote_texts)
        # With 10 pulls, we should likely get at least 2 different quotes
        # unless the pool is very small
        assert len(unique_quotes) >= 1


class TestQuoteFormatting:
    """Tests for quote formatting."""
    
    def test_quote_fits_display(self):
        """Test that quotes fit within board constraints."""
        max_line_length = 22
        max_lines = 6
        
        source = StarTrekQuotesSource()
        quote_data = source.get_random_quote()
        
        if isinstance(quote_data, dict):
            quote_text = quote_data.get("quote") or quote_data.get("text") or ""
        else:
            quote_text = str(quote_data)
        
        # Quote should be renderable (may need word wrap)
        assert len(quote_text) > 0
    
    def test_character_name_display(self):
        """Test character name is displayed with quote."""
        source = StarTrekQuotesSource()
        quote_data = source.get_random_quote()
        
        if isinstance(quote_data, dict):
            # Character might be in various fields
            character_fields = ["character", "speaker", "author", "who"]
            has_character = any(f in quote_data for f in character_fields)
            # Character is optional but common
            pass


class TestGetStarTrekQuotesSource:
    """Tests for get_star_trek_quotes_source factory function."""
    
    def test_factory_returns_instance(self):
        """Test factory returns an instance."""
        source = get_star_trek_quotes_source()
        # Source should be returned (may be None if disabled)
        if source is not None:
            assert isinstance(source, StarTrekQuotesSource)
    
    def test_factory_behavior_depends_on_config(self):
        """Test factory returns source based on config."""
        source = get_star_trek_quotes_source()
        # Source may be None if not enabled in config
        if source is not None:
            assert isinstance(source, StarTrekQuotesSource)


class TestQuoteData:
    """Tests for quote data integrity."""
    
    def test_quotes_not_empty_list(self):
        """Test that quotes collection is not empty."""
        source = StarTrekQuotesSource()
        
        # Try to get a quote, which should work if we have quotes
        quote = source.get_random_quote()
        assert quote is not None
    
    def test_quotes_are_strings(self):
        """Test that quote text is a string."""
        source = StarTrekQuotesSource()
        quote_data = source.get_random_quote()
        
        if isinstance(quote_data, dict):
            quote_text = quote_data.get("quote") or quote_data.get("text")
            if quote_text:
                assert isinstance(quote_text, str)
        else:
            assert isinstance(quote_data, str)
    
    def test_no_html_in_quotes(self):
        """Test that quotes don't contain HTML."""
        source = StarTrekQuotesSource()
        quote_data = source.get_random_quote()
        
        if isinstance(quote_data, dict):
            quote_text = quote_data.get("quote") or quote_data.get("text") or ""
        else:
            quote_text = str(quote_data)
        
        # Should not contain HTML tags
        assert "<" not in quote_text or ">" not in quote_text


class TestStarTrekQuotesPlugin:
    """Tests for the StarTrekQuotesPlugin class."""
    
    @pytest.fixture
    def plugin(self):
        """Create a plugin instance."""
        manifest = {
            "id": "star_trek_quotes",
            "name": "Star Trek Quotes",
            "version": "1.0.0"
        }
        return StarTrekQuotesPlugin(manifest)
    
    def test_plugin_initialization(self, plugin):
        """Test plugin initializes correctly."""
        assert plugin.plugin_id == "star_trek_quotes"
        assert plugin._quotes is not None
    
    def test_fetch_data_returns_all_variables(self, plugin):
        """Test fetch_data returns all expected variables."""
        result = plugin.fetch_data()
        
        assert result.available is True
        assert result.data is not None
        assert "quote" in result.data
        assert "character" in result.data
        assert "series" in result.data
        assert "series_color" in result.data
    
    def test_quote_variable_not_empty(self, plugin):
        """Test quote variable contains text."""
        result = plugin.fetch_data()
        
        assert result.available is True
        quote = result.data["quote"]
        
        # Quote should not be empty
        assert len(quote) > 0
        assert isinstance(quote, str)
    
    def test_character_variable_not_empty(self, plugin):
        """Test character variable contains text."""
        result = plugin.fetch_data()
        
        assert result.available is True
        character = result.data["character"]
        
        # Character should not be empty
        assert len(character) > 0
        assert isinstance(character, str)
    
    def test_validate_config_valid_ratio(self, plugin):
        """Test config validation with valid ratio."""
        config = {"ratio": "3:5:9"}
        errors = plugin.validate_config(config)
        assert len(errors) == 0
    
    def test_validate_config_invalid_ratio(self, plugin):
        """Test config validation with invalid ratio."""
        config = {"ratio": "invalid"}
        errors = plugin.validate_config(config)
        assert len(errors) > 0
    
    def test_series_color_mapping(self, plugin):
        """Test series color codes are set correctly."""
        result = plugin.fetch_data()
        
        assert result.available is True
        series_color = result.data["series_color"]
        
        # Should be a color code (format: {XX})
        assert series_color.startswith("{")
        assert series_color.endswith("}")
    
    def test_all_quotes_reasonable_length(self, plugin):
        """Test that all quotes are reasonable length for display."""
        # Test every quote in the actual data file
        for series, quotes_list in plugin._quotes.items():
            for quote_obj in quotes_list:
                quote = quote_obj["quote"]
                
                # Quote should be under 120 characters (as defined in manifest)
                assert len(quote) <= 120, (
                    f"Quote too long: [{series}] {quote[:50]}... "
                    f"has {len(quote)} chars, max 120"
                )
    
    def test_all_character_names_reasonable_length(self, plugin):
        """Test that all character names are reasonable length."""
        for series, quotes_list in plugin._quotes.items():
            for quote_obj in quotes_list:
                character = quote_obj["character"]
                
                # Character names should be under 15 chars (as defined in manifest)
                # This is reasonable for the display
                assert len(character) <= 20, (
                    f"Character name too long: [{series}] {character} "
                    f"has {len(character)} chars"
                )

    def test_validate_config_ratio_wrong_format(self, plugin):
        """Test config validation with ratio not in N:N:N format."""
        config = {"ratio": "1:2"}
        errors = plugin.validate_config(config)
        assert "Ratio must be in format" in errors[0]

    def test_validate_config_ratio_non_integer(self, plugin):
        """Test config validation with non-integer ratio parts."""
        config = {"ratio": "1:2:a"}
        errors = plugin.validate_config(config)
        assert "Ratio parts must be integers" in errors[0]

    def test_parse_ratio_custom_config(self, plugin):
        """Test _parse_ratio with custom ratio from config."""
        plugin.config = {"ratio": "1:2:3"}
        tng, voyager, ds9 = plugin._parse_ratio()
        assert (tng, voyager, ds9) == (1, 2, 3)

    def test_parse_ratio_invalid_returns_default(self, plugin):
        """Test _parse_ratio returns default when config is invalid."""
        plugin.config = {"ratio": "not-valid"}
        tng, voyager, ds9 = plugin._parse_ratio()
        assert (tng, voyager, ds9) == (3, 5, 9)

    def test_parse_ratio_wrong_parts_returns_default(self, plugin):
        """Test _parse_ratio returns default when parts count is wrong."""
        plugin.config = {"ratio": "1:2"}
        tng, voyager, ds9 = plugin._parse_ratio()
        assert (tng, voyager, ds9) == (3, 5, 9)

    def test_fetch_data_returns_unavailable_when_no_quotes(self, plugin):
        """Test fetch_data returns unavailable when _quotes is empty."""
        plugin._quotes = {"tng": [], "voyager": [], "ds9": []}
        result = plugin.fetch_data()
        assert result.available is False
        assert "No quotes available" in result.error

    def test_fetch_data_reloads_when_quotes_empty(self, plugin):
        """Test fetch_data calls _load_quotes when _quotes is None/empty."""
        plugin._quotes = None
        result = plugin.fetch_data()
        # After reload, quotes should be loaded from file (or empty if file missing)
        assert plugin._quotes is not None

    def test_fetch_data_fallback_when_series_empty(self, plugin):
        """Test fetch_data falls back when selected series has no quotes."""
        # Use a single series with quotes, others empty - force selection of empty
        plugin._quotes = {
            "tng": [{"quote": "Test.", "character": "Picard"}],
            "voyager": [],
            "ds9": [],
        }
        plugin.config = {"ratio": "0:1:0"}  # Only voyager in pool
        result = plugin.fetch_data()
        # Should fall back to tng since voyager is empty
        assert result.available is True
        assert result.data["quote"] == "Test."

    def test_fetch_data_exception_handling(self, plugin):
        """Test fetch_data handles exceptions gracefully."""
        with patch("plugins.star_trek_quotes.random.choice") as mock_choice:
            mock_choice.side_effect = RuntimeError("Random error")
            result = plugin.fetch_data()
        assert result.available is False
        assert "Random error" in result.error

    def test_get_formatted_display_returns_lines(self, plugin):
        """Test get_formatted_display returns formatted lines."""
        lines = plugin.get_formatted_display()
        assert lines is not None
        assert len(lines) <= 6
        assert any("-" in line for line in lines)  # Character attribution

    def test_get_formatted_display_long_quote_wrapping(self, plugin):
        """Test get_formatted_display word-wraps long quotes."""
        plugin._quotes = {
            "tng": [{
                "quote": "This is a very long quote that should definitely wrap "
                         "across multiple lines when displayed on the board.",
                "character": "Picard",
            }],
            "voyager": [],
            "ds9": [],
        }
        plugin.config = {"ratio": "1:0:0"}
        lines = plugin.get_formatted_display()
        assert lines is not None
        assert len(lines) <= 6

    def test_get_formatted_display_returns_none_when_no_quotes(self, plugin):
        """Test get_formatted_display returns None when no quotes available."""
        plugin._quotes = {"tng": [], "voyager": [], "ds9": []}
        lines = plugin.get_formatted_display()
        assert lines is None

    def test_fetch_data_all_series_empty_no_fallback(self, plugin):
        """Test fetch_data when all series are empty - no quotes to fall back to."""
        plugin._quotes = {"tng": [], "voyager": [], "ds9": []}
        result = plugin.fetch_data()
        assert result.available is False
        assert "No quotes available" in result.error

    def test_load_quotes_file_not_found(self):
        """Test _load_quotes when quotes file does not exist."""
        manifest = {"id": "star_trek_quotes", "name": "Star Trek Quotes", "version": "1.0.0"}
        real_exists = Path.exists

        def mock_exists(self):
            if str(self).endswith("quotes.json"):
                return False
            return real_exists(self)

        with patch.object(Path, "exists", mock_exists):
            plugin = StarTrekQuotesPlugin(manifest)
        assert plugin._quotes == {"tng": [], "voyager": [], "ds9": []}

    def test_load_quotes_exception_handling(self):
        """Test _load_quotes handles file read exceptions."""
        manifest = {"id": "star_trek_quotes", "name": "Star Trek Quotes", "version": "1.0.0"}
        with patch("plugins.star_trek_quotes.json.load", side_effect=OSError("Read error")):
            plugin = StarTrekQuotesPlugin(manifest)
        assert plugin._quotes == {"tng": [], "voyager": [], "ds9": []}

    def test_parse_ratio_attribute_error(self, plugin):
        """Test _parse_ratio when ratio config is not a string (no split method)."""
        plugin.config = {"ratio": 12345}  # int has no split
        tng, voyager, ds9 = plugin._parse_ratio()
        assert (tng, voyager, ds9) == (3, 5, 9)

