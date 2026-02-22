"""Unit tests for Stocks data source."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.utils.stocks import StocksSource, TIME_WINDOW_MAP, POPULAR_STOCKS


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

