"""Unit tests for Stocks data source and plugin."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.utils.stocks import StocksSource, TIME_WINDOW_MAP, POPULAR_STOCKS

from plugins.stocks import StocksPlugin, Plugin, TIME_WINDOW_MAP as PLUGIN_TIME_WINDOW_MAP


class TestStocksPlugin:
    """Tests for the StocksPlugin (plugins/stocks/__init__.py)."""

    def test_init(self):
        """Test plugin initialization."""
        plugin = StocksPlugin(manifest={"id": "stocks", "name": "Stock Prices"})
        assert plugin._cache is None

    def test_plugin_id(self):
        """Test plugin_id property."""
        plugin = StocksPlugin(manifest={})
        assert plugin.plugin_id == "stocks"

    def test_validate_config_empty_symbols(self):
        """Test validation with no symbols."""
        plugin = StocksPlugin(manifest={})
        errors = plugin.validate_config({"symbols": []})
        assert "At least one stock symbol is required" in errors

    def test_validate_config_too_many_symbols(self):
        """Test validation with more than 5 symbols."""
        plugin = StocksPlugin(manifest={})
        errors = plugin.validate_config({
            "symbols": ["A", "B", "C", "D", "E", "F"]
        })
        assert "Maximum 5 stock symbols allowed" in errors

    def test_validate_config_invalid_time_window(self):
        """Test validation with invalid time window."""
        plugin = StocksPlugin(manifest={})
        errors = plugin.validate_config({
            "symbols": ["AAPL"],
            "time_window": "Invalid Window"
        })
        assert "Invalid time window: Invalid Window" in errors

    def test_validate_config_valid(self):
        """Test validation with valid config."""
        plugin = StocksPlugin(manifest={})
        errors = plugin.validate_config({
            "symbols": ["AAPL", "GOOG"],
            "time_window": "1 Day"
        })
        assert errors == []

    def test_validate_config_default_time_window(self):
        """Test validation uses default time window when not specified."""
        plugin = StocksPlugin(manifest={})
        errors = plugin.validate_config({"symbols": ["AAPL"]})
        assert errors == []

    def test_fetch_data_yfinance_import_error(self):
        """Test fetch_data when yfinance is not installed."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "yfinance":
                raise ImportError("No module named 'yfinance'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            plugin = StocksPlugin(manifest={})
            plugin.config = {"symbols": ["AAPL"]}
            result = plugin.fetch_data()
        assert result.available is False
        assert "yfinance" in result.error

    def test_fetch_data_no_symbols(self):
        """Test fetch_data with no symbols configured."""
        plugin = StocksPlugin(manifest={})
        plugin.config = {"symbols": []}
        result = plugin.fetch_data()
        assert result.available is False
        assert "No stock symbols configured" in result.error

    @patch("yfinance.Ticker")
    def test_fetch_data_success(self, mock_ticker_class):
        """Test successful fetch_data."""
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "regularMarketPrice": 150.0,
            "longName": "Apple Inc."
        }
        import pandas as pd
        mock_hist = pd.DataFrame({
            "Close": [145.0, 148.0, 149.0, 149.5, 150.0]
        })
        mock_ticker.history.return_value = mock_hist
        mock_ticker_class.return_value = mock_ticker

        plugin = StocksPlugin(manifest={})
        plugin.config = {"symbols": ["AAPL"], "time_window": "1 Day"}
        result = plugin.fetch_data()

        assert result.available is True
        assert result.data["symbol"] == "AAPL"
        assert result.data["current_price"] == 150.0
        assert result.data["symbol_count"] == 1
        assert "stocks" in result.data
        assert plugin._cache is not None

    @patch("yfinance.Ticker")
    def test_fetch_data_all_fail(self, mock_ticker_class):
        """Test fetch_data when all stocks fail to fetch."""
        mock_ticker = MagicMock()
        mock_ticker.info = {}
        mock_ticker.history.return_value = __import__("pandas").DataFrame()
        mock_ticker_class.return_value = mock_ticker

        plugin = StocksPlugin(manifest={})
        plugin.config = {"symbols": ["INVALID"]}
        result = plugin.fetch_data()

        assert result.available is False
        assert "Failed to fetch any stock data" in result.error

    @patch("yfinance.Ticker")
    def test_fetch_data_exception(self, mock_ticker_class):
        """Test fetch_data when an exception is raised in main flow."""
        mock_ticker = MagicMock()
        mock_ticker.info = {"regularMarketPrice": 100.0, "longName": "Test"}
        import pandas as pd
        mock_ticker.history.return_value = pd.DataFrame({"Close": [99.0, 100.0]})
        mock_ticker_class.return_value = mock_ticker

        plugin = StocksPlugin(manifest={})
        plugin.config = {"symbols": ["AAPL"]}
        with patch.object(plugin, "_align_formatting", side_effect=RuntimeError("Format error")):
            result = plugin.fetch_data()

        assert result.available is False
        assert "Format error" in result.error

    @patch("yfinance.Ticker")
    def test_fetch_single_stock_no_price(self, mock_ticker_class):
        """Test _fetch_single_stock when no price is available."""
        mock_ticker = MagicMock()
        mock_ticker.info = {}
        mock_ticker_class.return_value = mock_ticker

        plugin = StocksPlugin(manifest={})
        result = plugin._fetch_single_stock("INVALID", "1d")
        assert result is None

    @patch("yfinance.Ticker")
    def test_fetch_single_stock_current_price_fallback(self, mock_ticker_class):
        """Test _fetch_single_stock uses currentPrice when regularMarketPrice missing."""
        mock_ticker = MagicMock()
        mock_ticker.info = {"currentPrice": 99.50, "longName": "Test Corp"}
        import pandas as pd
        mock_ticker.history.return_value = pd.DataFrame({
            "Close": [98.0, 99.0, 99.25, 99.50]
        })
        mock_ticker_class.return_value = mock_ticker

        plugin = StocksPlugin(manifest={})
        result = plugin._fetch_single_stock("TEST", "5d")
        assert result is not None
        assert result["current_price"] == 99.50
        assert result["previous_price"] == 98.0  # iloc[0] for non-1d period

    @patch("yfinance.Ticker")
    def test_fetch_single_stock_empty_history(self, mock_ticker_class):
        """Test _fetch_single_stock with empty history."""
        mock_ticker = MagicMock()
        mock_ticker.info = {"regularMarketPrice": 100.0}
        mock_ticker.history.return_value = __import__("pandas").DataFrame()
        mock_ticker_class.return_value = mock_ticker

        plugin = StocksPlugin(manifest={})
        result = plugin._fetch_single_stock("TEST", "1d")
        assert result is None

    @patch("yfinance.Ticker")
    def test_fetch_single_stock_1d_period_uses_second_to_last(self, mock_ticker_class):
        """Test _fetch_single_stock with 1d period uses second-to-last close."""
        mock_ticker = MagicMock()
        mock_ticker.info = {"regularMarketPrice": 150.0, "longName": "Test"}
        import pandas as pd
        mock_hist = pd.DataFrame({"Close": [140.0, 145.0, 148.0, 149.0, 150.0]})
        mock_ticker.history.return_value = mock_hist
        mock_ticker_class.return_value = mock_ticker

        plugin = StocksPlugin(manifest={})
        result = plugin._fetch_single_stock("TEST", "1d")
        assert result["previous_price"] == 149.0  # iloc[-2]
        assert result["change_percent"] == pytest.approx(0.67, abs=0.1)

    @patch("yfinance.Ticker")
    def test_fetch_single_stock_previous_price_zero(self, mock_ticker_class):
        """Test _fetch_single_stock when previous price is zero."""
        mock_ticker = MagicMock()
        mock_ticker.info = {"regularMarketPrice": 100.0, "longName": "Test"}
        import pandas as pd
        mock_hist = pd.DataFrame({"Close": [0.0, 0.0, 100.0]})
        mock_ticker.history.return_value = mock_hist
        mock_ticker_class.return_value = mock_ticker

        plugin = StocksPlugin(manifest={})
        result = plugin._fetch_single_stock("TEST", "5d")
        assert result["change_percent"] == 0.0
        assert result["change_direction"] == "up"

    @patch("yfinance.Ticker")
    def test_fetch_single_stock_negative_change_red_color(self, mock_ticker_class):
        """Test _fetch_single_stock with negative change uses red color."""
        mock_ticker = MagicMock()
        mock_ticker.info = {"regularMarketPrice": 95.0, "longName": "Test"}
        import pandas as pd
        mock_hist = pd.DataFrame({"Close": [100.0, 98.0, 97.0, 96.0, 95.0]})
        mock_ticker.history.return_value = mock_hist
        mock_ticker_class.return_value = mock_ticker

        plugin = StocksPlugin(manifest={})
        result = plugin._fetch_single_stock("TEST", "1d")
        assert result["color_tile"] == "{63}"
        assert result["change_direction"] == "down"

    @patch("yfinance.Ticker")
    def test_fetch_single_stock_zero_change_white_color(self, mock_ticker_class):
        """Test _fetch_single_stock with zero change uses white color."""
        mock_ticker = MagicMock()
        mock_ticker.info = {"regularMarketPrice": 100.0, "longName": "Test"}
        import pandas as pd
        mock_hist = pd.DataFrame({"Close": [100.0, 100.0, 100.0, 100.0, 100.0]})
        mock_ticker.history.return_value = mock_hist
        mock_ticker_class.return_value = mock_ticker

        plugin = StocksPlugin(manifest={})
        result = plugin._fetch_single_stock("TEST", "1d")
        assert result["color_tile"] == "{69}"
        assert result["change_direction"] == "up"

    @patch("yfinance.Ticker")
    def test_fetch_single_stock_short_name_fallback(self, mock_ticker_class):
        """Test _fetch_single_stock uses shortName when longName missing."""
        mock_ticker = MagicMock()
        mock_ticker.info = {"regularMarketPrice": 100.0, "shortName": "TEST"}
        import pandas as pd
        mock_ticker.history.return_value = pd.DataFrame({"Close": [99.0, 100.0]})
        mock_ticker_class.return_value = mock_ticker

        plugin = StocksPlugin(manifest={})
        result = plugin._fetch_single_stock("test", "5d")
        assert result["company_name"] == "TEST"
        assert result["symbol"] == "TEST"

    @patch("yfinance.Ticker")
    def test_fetch_single_stock_symbol_fallback_for_company_name(self, mock_ticker_class):
        """Test _fetch_single_stock uses symbol when no name available."""
        mock_ticker = MagicMock()
        mock_ticker.info = {"regularMarketPrice": 100.0}
        import pandas as pd
        mock_ticker.history.return_value = pd.DataFrame({"Close": [99.0, 100.0]})
        mock_ticker_class.return_value = mock_ticker

        plugin = StocksPlugin(manifest={})
        result = plugin._fetch_single_stock("XYZ", "5d")
        assert result["company_name"] == "XYZ"

    @patch("yfinance.Ticker")
    def test_fetch_single_stock_exception_returns_none(self, mock_ticker_class):
        """Test _fetch_single_stock returns None on exception."""
        mock_ticker_class.side_effect = ValueError("Ticker error")

        plugin = StocksPlugin(manifest={})
        result = plugin._fetch_single_stock("BAD", "1d")
        assert result is None

    def test_align_formatting_empty(self):
        """Test _align_formatting with empty list."""
        plugin = StocksPlugin(manifest={})
        result = plugin._align_formatting([])
        assert result == []

    def test_align_formatting_single_stock(self):
        """Test _align_formatting with single stock."""
        plugin = StocksPlugin(manifest={})
        stocks = [{
            "symbol": "AAPL",
            "current_price": 150.0,
            "previous_price": 148.0,
            "change_percent": 1.35,
            "color_tile": "{66}",
        }]
        result = plugin._align_formatting(stocks)
        assert result[0]["formatted"] == "AAPL{66} $150.00 +1.35%"

    def test_align_formatting_multiple_stocks(self):
        """Test _align_formatting aligns columns across stocks."""
        plugin = StocksPlugin(manifest={})
        stocks = [
            {"symbol": "GOOG", "current_price": 1234.56, "change_percent": 2.5, "color_tile": "{66}"},
            {"symbol": "AAPL", "current_price": 175.25, "change_percent": -0.5, "color_tile": "{63}"},
        ]
        result = plugin._align_formatting(stocks)
        assert "1234.56" in result[0]["formatted"]
        assert "175.25" in result[1]["formatted"]
        assert "+2.50%" in result[0]["formatted"]
        assert "-0.50%" in result[1]["formatted"]

    @patch("yfinance.Ticker")
    def test_get_formatted_display_no_cache_fetches(self, mock_ticker_class):
        """Test get_formatted_display fetches when cache is empty."""
        mock_ticker = MagicMock()
        mock_ticker.info = {"regularMarketPrice": 100.0, "longName": "Test"}
        import pandas as pd
        mock_ticker.history.return_value = pd.DataFrame({"Close": [99.0, 100.0]})
        mock_ticker_class.return_value = mock_ticker

        plugin = StocksPlugin(manifest={})
        plugin.config = {"symbols": ["TEST"], "time_window": "1 Day"}
        lines = plugin.get_formatted_display()

        assert lines is not None
        assert "STOCKS" in lines[0]
        assert len(lines) == 6

    def test_get_formatted_display_uses_cache(self):
        """Test get_formatted_display uses cache when available."""
        plugin = StocksPlugin(manifest={})
        plugin._cache = {
            "stocks": [
                {"formatted": "AAPL{66} $150.00 +1.00%", "symbol": "AAPL"},
            ]
        }
        lines = plugin.get_formatted_display()
        assert "AAPL" in lines[2]
        assert "STOCKS" in lines[0]

    def test_get_formatted_display_truncates_to_22_chars(self):
        """Test get_formatted_display truncates stock lines to 22 chars."""
        plugin = StocksPlugin(manifest={})
        plugin._cache = {
            "stocks": [
                {"formatted": "AAPL{66} $12345.67 +123.45%", "symbol": "AAPL"},
            ]
        }
        lines = plugin.get_formatted_display()
        assert len(lines[2]) == 22

    def test_get_formatted_display_max_4_stocks(self):
        """Test get_formatted_display shows max 4 stocks."""
        plugin = StocksPlugin(manifest={})
        plugin._cache = {
            "stocks": [
                {"formatted": "A{66} $1.00 +0%", "symbol": "A"},
                {"formatted": "B{66} $2.00 +0%", "symbol": "B"},
                {"formatted": "C{66} $3.00 +0%", "symbol": "C"},
                {"formatted": "D{66} $4.00 +0%", "symbol": "D"},
                {"formatted": "E{66} $5.00 +0%", "symbol": "E"},
            ]
        }
        lines = plugin.get_formatted_display()
        assert len([l for l in lines if l and l != "STOCKS" and not l.isspace()]) == 5  # STOCKS + blank + 4 stocks

    def test_get_formatted_display_fetch_fails_returns_none(self):
        """Test get_formatted_display returns None when fetch fails."""
        plugin = StocksPlugin(manifest={})
        plugin._cache = None
        plugin.config = {"symbols": []}
        lines = plugin.get_formatted_display()
        assert lines is None

    def test_get_formatted_display_empty_cache_data_returns_none(self):
        """Test get_formatted_display returns None when cache has empty/falsy data."""
        plugin = StocksPlugin(manifest={})
        plugin._cache = {}  # Empty dict is falsy, triggers early return
        lines = plugin.get_formatted_display()
        assert lines is None

    def test_plugin_export(self):
        """Test Plugin export is StocksPlugin."""
        assert Plugin is StocksPlugin

    def test_time_window_map(self):
        """Test TIME_WINDOW_MAP has expected mappings."""
        assert PLUGIN_TIME_WINDOW_MAP["1 Day"] == "1d"
        assert PLUGIN_TIME_WINDOW_MAP["ALL"] == "max"
        assert PLUGIN_TIME_WINDOW_MAP["5 Years"] == "5y"


class TestStocksSource:
    """Test Stocks data source."""
    
    def test_init(self):
        """Test source initialization."""
        source = StocksSource(
            symbols=["GOOG", "AAPL"],
            time_window="1 Day",
            finnhub_api_key=""
        )
        assert source.symbols == ["GOOG", "AAPL"]
        assert source.time_window == "1 Day"
        assert source.finnhub_api_key == ""
    
    def test_init_single_symbol(self):
        """Test initialization with single symbol string."""
        source = StocksSource(
            symbols="GOOG",
            time_window="1 Day"
        )
        assert source.symbols == ["GOOG"]
    
    def test_init_max_symbols(self):
        """Test that symbols are limited to 5 max."""
        source = StocksSource(
            symbols=["GOOG", "AAPL", "MSFT", "TSLA", "AMZN", "META"],  # 6 symbols
            time_window="1 Day"
        )
        assert len(source.symbols) == 5
        assert source.symbols == ["GOOG", "AAPL", "MSFT", "TSLA", "AMZN"]
    
    def test_init_empty_symbols(self):
        """Test initialization with empty symbols."""
        source = StocksSource(symbols=[], time_window="1 Day")
        assert source.symbols == []
    
    def test_time_window_mapping(self):
        """Test time window to yfinance period mapping."""
        source = StocksSource(symbols=["GOOG"], time_window="1 Day")
        assert source._map_time_window_to_yfinance("1 Day") == "1d"
        assert source._map_time_window_to_yfinance("5 Days") == "5d"
        assert source._map_time_window_to_yfinance("1 Month") == "1mo"
        assert source._map_time_window_to_yfinance("ALL") == "max"
        assert source._map_time_window_to_yfinance("Unknown") == "1d"  # Default
    
    def test_format_price(self):
        """Test price formatting to 2 decimal places."""
        assert StocksSource._format_price(150.25) == "150.25"
        assert StocksSource._format_price(1234.567) == "1234.57"  # Rounded
        assert StocksSource._format_price(0.99) == "0.99"
        assert StocksSource._format_price(1000.0) == "1000.00"
    
    def test_format_percentage(self):
        """Test percentage formatting with + or - sign."""
        assert StocksSource._format_percentage(1.18) == "+1.18%"
        assert StocksSource._format_percentage(-2.34) == "-2.34%"
        assert StocksSource._format_percentage(0.0) == "+0.00%"
        assert StocksSource._format_percentage(12.5) == "+12.50%"
        assert StocksSource._format_percentage(-0.01) == "-0.01%"
    
    @patch('src.utils.stocks.yf.Ticker')
    def test_fetch_single_stock_success(self, mock_ticker_class):
        """Test successful single stock data fetch."""
        # Mock yfinance Ticker
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "regularMarketPrice": 150.25,
            "longName": "Alphabet Inc."
        }
        
        # Mock historical data
        # For "1d" period, we fetch 5d of history and use second-to-last close as previous
        import pandas as pd
        mock_hist = pd.DataFrame({
            "Close": [145.00, 148.07, 149.50, 150.00, 150.25]
        })
        mock_ticker.history.return_value = mock_hist
        
        mock_ticker_class.return_value = mock_ticker
        
        source = StocksSource(symbols=["GOOG"], time_window="1 Day")
        result = source._fetch_single_stock("GOOG", "1d")
        
        assert result is not None
        assert result["symbol"] == "GOOG"
        assert result["current_price"] == 150.25
        # Previous price should be second-to-last (yesterday's close): 150.00
        assert result["previous_price"] == 150.00
        assert result["change_percent"] == pytest.approx(0.17, abs=0.01)  # (150.25 - 150.00) / 150.00 * 100
        assert result["change_direction"] == "up"
        assert result["company_name"] == "Alphabet Inc."
        assert "{green}" in result["formatted"]  # Positive change = green
        assert "GOOG" in result["formatted"]
        assert "150.25" in result["formatted"]
    
    @patch('src.utils.stocks.yf.Ticker')
    def test_fetch_single_stock_negative_change(self, mock_ticker_class):
        """Test stock with negative change (red color)."""
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "regularMarketPrice": 100.0,
            "longName": "Test Corp"
        }
        
        import pandas as pd
        # For "1d" period, mock 5 days of data, second-to-last is yesterday's close
        mock_hist = pd.DataFrame({
            "Close": [115.0, 112.0, 110.0, 105.0, 100.0]
        })
        mock_ticker.history.return_value = mock_hist
        mock_ticker_class.return_value = mock_ticker
        
        source = StocksSource(symbols=["TEST"], time_window="1 Day")
        result = source._fetch_single_stock("TEST", "1d")
        
        assert result is not None
        # Current: 100.0, Previous (second-to-last): 105.0
        assert result["previous_price"] == 105.0
        assert result["change_percent"] < 0
        assert result["change_direction"] == "down"
        assert "{red}" in result["formatted"]
    
    @patch('src.utils.stocks.yf.Ticker')
    def test_fetch_single_stock_zero_change(self, mock_ticker_class):
        """Test stock with zero change (white color)."""
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "regularMarketPrice": 100.0,
            "longName": "Test Corp"
        }
        
        import pandas as pd
        # For "1d" period, mock 5 days with second-to-last = 100.0
        mock_hist = pd.DataFrame({
            "Close": [100.0, 100.0, 100.0, 100.0, 100.0]
        })
        mock_ticker.history.return_value = mock_hist
        mock_ticker_class.return_value = mock_ticker
        
        source = StocksSource(symbols=["TEST"], time_window="1 Day")
        result = source._fetch_single_stock("TEST", "1d")
        
        assert result is not None
        assert result["previous_price"] == 100.0
        assert result["change_percent"] == pytest.approx(0.0, abs=0.01)
        assert result["change_direction"] == "up"  # 0 is considered "up"
        assert "{white}" in result["formatted"]
    
    @patch('src.utils.stocks.yf.Ticker')
    def test_fetch_single_stock_no_price(self, mock_ticker_class):
        """Test stock with no current price available."""
        mock_ticker = MagicMock()
        mock_ticker.info = {}  # No price info
        mock_ticker_class.return_value = mock_ticker
        
        source = StocksSource(symbols=["INVALID"], time_window="1 Day")
        result = source._fetch_single_stock("INVALID", "1d")
        
        assert result is None
    
    @patch('src.utils.stocks.yf.Ticker')
    def test_fetch_single_stock_no_history(self, mock_ticker_class):
        """Test stock with no historical data."""
        mock_ticker = MagicMock()
        mock_ticker.info = {"regularMarketPrice": 100.0}
        
        import pandas as pd
        mock_ticker.history.return_value = pd.DataFrame()  # Empty DataFrame
        mock_ticker_class.return_value = mock_ticker
        
        source = StocksSource(symbols=["TEST"], time_window="1 Day")
        result = source._fetch_single_stock("TEST", "1d")
        
        assert result is None
    
    @patch('src.utils.stocks.yf.Ticker')
    def test_fetch_stocks_data_alignment(self, mock_ticker_class):
        """Test that multiple stocks are aligned in columns."""
        # Mock different stocks with different price ranges
        def create_mock_ticker(symbol, current_price, previous_price):
            mock_ticker = MagicMock()
            mock_ticker.info = {
                "regularMarketPrice": current_price,
                "longName": f"{symbol} Corp"
            }
            
            import pandas as pd
            # For "1d" period, create 5 days with second-to-last as previous_price
            mock_hist = pd.DataFrame({
                "Close": [previous_price * 0.95, previous_price * 0.97, previous_price * 0.99, previous_price, current_price]
            })
            mock_ticker.history.return_value = mock_hist
            return mock_ticker
        
        # Setup mocks for different price ranges
        mock_ticker_class.side_effect = [
            create_mock_ticker("GOOG", 1234.56, 1200.0),  # High price
            create_mock_ticker("AAPL", 273.08, 270.0),   # Medium price
            create_mock_ticker("TSLA", 45.43, 44.0),     # Lower price
        ]
        
        source = StocksSource(
            symbols=["GOOG", "AAPL", "TSLA"],
            time_window="1 Day"
        )
        
        results = source.fetch_stocks_data()
        
        assert len(results) == 3
        
        # Check that all formatted strings have aligned prices and percentages
        formatted_strings = [r["formatted"] for r in results]
        
        # Format: SYMBOL{color} $PRICE PERCENTAGE
        # After alignment with rjust, prices and percentages should have consistent widths
        # The rjust adds leading spaces, so we need to extract the full aligned sections
        
        price_widths = []
        percent_widths = []
        
        for fmt in formatted_strings:
            # Format: SYMBOL{color} $PRICE PERCENTAGE
            # Find the closing brace of color tile (e.g., {green} ends at })
            color_end = fmt.find("}")
            if color_end == -1:
                continue
            
            # The space after color tile is right after the }
            space_after_color = color_end + 1
            if space_after_color >= len(fmt) or fmt[space_after_color] != " ":
                continue
            
            # Find $ which marks where the actual price starts (may have leading spaces before it from rjust)
            dollar_idx = fmt.find("$", space_after_color)
            if dollar_idx == -1:
                continue
            
            # Find the space after the price (before percentage)
            space_after_price = fmt.find(" ", dollar_idx)
            if space_after_price == -1:
                continue
            
            # Extract the full price section (from space after color to space after price)
            # This includes any leading spaces from rjust padding
            price_section = fmt[space_after_color + 1:space_after_price]
            price_widths.append(len(price_section))
            
            # Find % to get percentage section
            percent_idx = fmt.find("%", space_after_price)
            if percent_idx != -1:
                # Extract percentage section (from space after price to %)
                # This may also include leading spaces from rjust
                percent_section = fmt[space_after_price + 1:percent_idx + 1]
                percent_widths.append(len(percent_section))
        
        # Debug: print the actual strings to verify alignment
        # All prices should have the same width (right-aligned with rjust padding)
        assert len(set(price_widths)) == 1, (
            f"Prices should be aligned (widths: {price_widths}, "
            f"formatted strings: {formatted_strings})"
        )
        
        # All percentages should have the same width (right-aligned with rjust padding)
        assert len(set(percent_widths)) == 1, (
            f"Percentages should be aligned (widths: {percent_widths}, "
            f"formatted strings: {formatted_strings})"
        )
        
        # Verify the formatted strings contain expected elements
        assert any("GOOG" in f for f in formatted_strings)
        assert any("AAPL" in f for f in formatted_strings)
        assert any("TSLA" in f for f in formatted_strings)
    
    @patch('src.utils.stocks.yf.Ticker')
    def test_fetch_stocks_data_empty_symbols(self, mock_ticker_class):
        """Test fetch with empty symbols list."""
        source = StocksSource(symbols=[], time_window="1 Day")
        results = source.fetch_stocks_data()
        
        assert results == []
        mock_ticker_class.assert_not_called()
    
    @patch('src.utils.stocks.yf.Ticker')
    def test_fetch_stocks_data_partial_failure(self, mock_ticker_class):
        """Test fetch when some symbols fail."""
        def create_mock_ticker(symbol, current_price, previous_price, has_price=True, has_history=True):
            mock_ticker = MagicMock()
            if has_price:
                mock_ticker.info = {
                    "regularMarketPrice": current_price,
                    "longName": f"{symbol} Corp"
                }
            else:
                mock_ticker.info = {}
            
            import pandas as pd
            if has_history:
                # For "1d" period, create 5 days with second-to-last as previous_price
                mock_hist = pd.DataFrame({
                    "Close": [previous_price * 0.95, previous_price * 0.97, previous_price * 0.99, previous_price, current_price]
                })
            else:
                mock_hist = pd.DataFrame()
            mock_ticker.history.return_value = mock_hist
            return mock_ticker
        
        mock_ticker_class.side_effect = [
            create_mock_ticker("GOOG", 150.0, 148.0, has_price=True, has_history=True),
            create_mock_ticker("INVALID", 0, 0, has_price=False, has_history=False),  # Fails
            create_mock_ticker("AAPL", 200.0, 198.0, has_price=True, has_history=True),
        ]
        
        source = StocksSource(
            symbols=["GOOG", "INVALID", "AAPL"],
            time_window="1 Day"
        )
        
        results = source.fetch_stocks_data()
        
        # Should return 3 results (including placeholder for failed stock to maintain index alignment)
        assert len(results) == 3
        assert results[0]["symbol"] == "GOOG"
        assert results[1]["symbol"] == "INVALID"  # Placeholder for failed stock
        assert results[1]["current_price"] == 0.0  # Placeholder has 0.0 price
        assert results[2]["symbol"] == "AAPL"
    
    def test_validate_symbol_success(self):
        """Test symbol validation with valid symbol."""
        with patch('src.utils.stocks.yf.Ticker') as mock_ticker_class:
            mock_ticker = MagicMock()
            mock_ticker.info = {
                "symbol": "GOOG",
                "longName": "Alphabet Inc.",
                "regularMarketPrice": 150.25  # Need price for validation
            }
            mock_ticker_class.return_value = mock_ticker
            
            result = StocksSource.validate_symbol("GOOG")
            
            assert result["valid"] is True
            assert result["symbol"] == "GOOG"
            assert "Alphabet" in result.get("name", "")
    
    def test_validate_symbol_invalid(self):
        """Test symbol validation with invalid symbol."""
        with patch('src.utils.stocks.yf.Ticker') as mock_ticker_class:
            mock_ticker = MagicMock()
            mock_ticker.info = {}  # Empty info = invalid
            mock_ticker_class.return_value = mock_ticker
            
            result = StocksSource.validate_symbol("INVALID")
            
            assert result["valid"] is False
            assert result["symbol"] == "INVALID"
    
    def test_search_symbols_curated_list(self):
        """Test symbol search using curated list (no Finnhub)."""
        source = StocksSource(
            symbols=[],
            time_window="1 Day",
            finnhub_api_key=""  # No API key
        )
        
        results = source.search_symbols("AAP")
        
        # Should find AAPL in curated list
        assert len(results) > 0
        assert any(r["symbol"] == "AAPL" for r in results)
        assert any("Apple" in r.get("name", "") for r in results)
    
    def test_search_symbols_no_results(self):
        """Test symbol search with no matches."""
        source = StocksSource(
            symbols=[],
            time_window="1 Day",
            finnhub_api_key=""
        )
        
        results = source.search_symbols("ZZZZZZZ")
        
        assert results == []
    
    def test_search_symbols_with_finnhub_skipped(self):
        """Test symbol search with Finnhub API - skipped due to complex mocking."""
        # Note: Finnhub integration is tested via integration tests
        # Unit tests focus on curated list functionality
        pass
    
    def test_search_symbols_finnhub_fallback_skipped(self):
        """Test that search falls back to curated list if Finnhub fails - skipped."""
        # Note: Finnhub fallback is tested via integration tests
        pass

