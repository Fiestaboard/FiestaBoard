"""Stock market data source using yfinance (Yahoo Finance).

Supports multiple stock symbol monitoring with price and percentage change tracking.
Optional Finnhub integration for symbol search and autocomplete.
"""

import logging
import yfinance as yf
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Time window mapping: human-readable to yfinance period
TIME_WINDOW_MAP = {
    "1 Day": "1d",
    "5 Days": "5d",
    "1 Month": "1mo",
    "3 Months": "3mo",
    "6 Months": "6mo",
    "1 Year": "1y",
    "2 Years": "2y",
    "5 Years": "5y",
    "ALL": "max",  # All available history
}

# Popular US stocks for autocomplete (curated list)
POPULAR_STOCKS = [
    {"symbol": "AAPL", "name": "Apple Inc."},
    {"symbol": "GOOG", "name": "Alphabet Inc."},
    {"symbol": "GOOGL", "name": "Alphabet Inc. Class A"},
    {"symbol": "MSFT", "name": "Microsoft Corporation"},
    {"symbol": "AMZN", "name": "Amazon.com Inc."},
    {"symbol": "TSLA", "name": "Tesla, Inc."},
    {"symbol": "META", "name": "Meta Platforms Inc."},
    {"symbol": "NVDA", "name": "NVIDIA Corporation"},
    {"symbol": "JPM", "name": "JPMorgan Chase & Co."},
    {"symbol": "V", "name": "Visa Inc."},
    {"symbol": "JNJ", "name": "Johnson & Johnson"},
    {"symbol": "WMT", "name": "Walmart Inc."},
    {"symbol": "PG", "name": "The Procter & Gamble Company"},
    {"symbol": "MA", "name": "Mastercard Incorporated"},
    {"symbol": "UNH", "name": "UnitedHealth Group Incorporated"},
    {"symbol": "HD", "name": "The Home Depot, Inc."},
    {"symbol": "DIS", "name": "The Walt Disney Company"},
    {"symbol": "BAC", "name": "Bank of America Corp."},
    {"symbol": "ADBE", "name": "Adobe Inc."},
    {"symbol": "NFLX", "name": "Netflix, Inc."},
    {"symbol": "CRM", "name": "Salesforce, Inc."},
    {"symbol": "PYPL", "name": "PayPal Holdings, Inc."},
    {"symbol": "INTC", "name": "Intel Corporation"},
    {"symbol": "CMCSA", "name": "Comcast Corporation"},
    {"symbol": "PFE", "name": "Pfizer Inc."},
    {"symbol": "CSCO", "name": "Cisco Systems, Inc."},
    {"symbol": "PEP", "name": "PepsiCo, Inc."},
    {"symbol": "TMO", "name": "Thermo Fisher Scientific Inc."},
    {"symbol": "COST", "name": "Costco Wholesale Corporation"},
    {"symbol": "ABBV", "name": "AbbVie Inc."},
    {"symbol": "AVGO", "name": "Broadcom Inc."},
    {"symbol": "TXN", "name": "Texas Instruments Incorporated"},
    {"symbol": "NKE", "name": "Nike, Inc."},
    {"symbol": "QCOM", "name": "QUALCOMM Incorporated"},
    {"symbol": "MDT", "name": "Medtronic plc"},
    {"symbol": "HON", "name": "Honeywell International Inc."},
    {"symbol": "AMGN", "name": "Amgen Inc."},
    {"symbol": "SBUX", "name": "Starbucks Corporation"},
    {"symbol": "BMY", "name": "Bristol-Myers Squibb Company"},
    {"symbol": "GILD", "name": "Gilead Sciences, Inc."},
    {"symbol": "LMT", "name": "Lockheed Martin Corporation"},
    {"symbol": "RTX", "name": "RTX Corporation"},
    {"symbol": "DE", "name": "Deere & Company"},
    {"symbol": "CAT", "name": "Caterpillar Inc."},
    {"symbol": "GE", "name": "General Electric Company"},
    {"symbol": "F", "name": "Ford Motor Company"},
    {"symbol": "GM", "name": "General Motors Company"},
    {"symbol": "XOM", "name": "Exxon Mobil Corporation"},
    {"symbol": "CVX", "name": "Chevron Corporation"},
    {"symbol": "COP", "name": "ConocoPhillips"},
    {"symbol": "SLB", "name": "Schlumberger Limited"},
    {"symbol": "EOG", "name": "EOG Resources, Inc."},
    {"symbol": "MPC", "name": "Marathon Petroleum Corporation"},
    {"symbol": "VLO", "name": "Valero Energy Corporation"},
    {"symbol": "PSX", "name": "Phillips 66"},
    {"symbol": "HES", "name": "Hess Corporation"},
    {"symbol": "MRO", "name": "Marathon Oil Corporation"},
    {"symbol": "OXY", "name": "Occidental Petroleum Corporation"},
    {"symbol": "DVN", "name": "Devon Energy Corporation"},
    {"symbol": "APA", "name": "APA Corporation"},
    {"symbol": "FANG", "name": "Diamondback Energy, Inc."},
    {"symbol": "CTRA", "name": "Coterra Energy Inc."},
    {"symbol": "PR", "name": "Permian Resources Corporation"},
    {"symbol": "MTCH", "name": "Match Group, Inc."},
    {"symbol": "LYFT", "name": "Lyft, Inc."},
    {"symbol": "UBER", "name": "Uber Technologies, Inc."},
    {"symbol": "DASH", "name": "DoorDash, Inc."},
    {"symbol": "GRAB", "name": "Grab Holdings Limited"},
    {"symbol": "SPOT", "name": "Spotify Technology S.A."},
    {"symbol": "SNAP", "name": "Snap Inc."},
    {"symbol": "TWTR", "name": "Twitter, Inc."},
    {"symbol": "PINS", "name": "Pinterest, Inc."},
    {"symbol": "ROKU", "name": "Roku, Inc."},
    {"symbol": "ZM", "name": "Zoom Video Communications, Inc."},
    {"symbol": "DOCN", "name": "DigitalOcean Holdings, Inc."},
    {"symbol": "SNOW", "name": "Snowflake Inc."},
    {"symbol": "NET", "name": "Cloudflare, Inc."},
    {"symbol": "CRWD", "name": "CrowdStrike Holdings, Inc."},
    {"symbol": "ZS", "name": "Zscaler, Inc."},
    {"symbol": "OKTA", "name": "Okta, Inc."},
    {"symbol": "FTNT", "name": "Fortinet, Inc."},
    {"symbol": "PANW", "name": "Palo Alto Networks, Inc."},
    {"symbol": "CHKP", "name": "Check Point Software Technologies Ltd."},
    {"symbol": "VRSN", "name": "VeriSign, Inc."},
    {"symbol": "AKAM", "name": "Akamai Technologies, Inc."},
    {"symbol": "FFIV", "name": "F5, Inc."},
    {"symbol": "JNPR", "name": "Juniper Networks, Inc."},
    {"symbol": "ANET", "name": "Arista Networks, Inc."},
    {"symbol": "NTNX", "name": "Nutanix, Inc."},
    {"symbol": "VEEV", "name": "Veeva Systems Inc."},
    {"symbol": "WDAY", "name": "Workday, Inc."},
    {"symbol": "NOW", "name": "ServiceNow, Inc."},
    {"symbol": "TEAM", "name": "Atlassian Corporation"},
    {"symbol": "ASAN", "name": "Asana, Inc."},
    {"symbol": "MDB", "name": "MongoDB, Inc."},
    {"symbol": "ESTC", "name": "Elastic N.V."},
    {"symbol": "SPLK", "name": "Splunk Inc."},
    {"symbol": "NEWR", "name": "New Relic, Inc."},
    {"symbol": "DT", "name": "Dynatrace, Inc."},
    {"symbol": "PD", "name": "PagerDuty, Inc."},
    {"symbol": "QLYS", "name": "Qualys, Inc."},
    {"symbol": "RPD", "name": "Rapid7, Inc."},
    {"symbol": "TENB", "name": "Tenable Holdings, Inc."},
    {"symbol": "VRRM", "name": "Verra Mobility Corporation"},
    {"symbol": "ALRM", "name": "Alarm.com Holdings, Inc."},
]


class StocksSource:
    """Fetches stock market data using yfinance."""
    
    def __init__(
        self,
        symbols: List[str],
        time_window: str,
        finnhub_api_key: Optional[str] = None
    ):
        """
        Initialize stocks source.
        
        Args:
            symbols: List of stock symbols to monitor (max 5)
            time_window: Human-readable time window (e.g., "1 Day", "ALL")
            finnhub_api_key: Optional Finnhub API key for symbol search
        """
        # Limit to 5 symbols max
        if isinstance(symbols, list):
            self.symbols = symbols[:5] if len(symbols) > 5 else symbols
        elif isinstance(symbols, str):
            self.symbols = [symbols] if symbols else []
        else:
            self.symbols = []
        
        self.time_window = time_window
        self.finnhub_api_key = finnhub_api_key
    
    @staticmethod
    def _map_time_window_to_yfinance(time_window: str) -> str:
        """
        Map human-readable time window to yfinance period.
        
        Args:
            time_window: Human-readable format (e.g., "1 Day", "ALL")
            
        Returns:
            yfinance period string (e.g., "1d", "max")
        """
        return TIME_WINDOW_MAP.get(time_window, "1d")
    
    @staticmethod
    def _format_price(price: float) -> str:
        """
        Format price to always show 2 decimal places.
        
        Args:
            price: Price value
            
        Returns:
            Formatted price string (e.g., "150.25")
        """
        return f"{price:.2f}"
    
    @staticmethod
    def _format_percentage(change_percent: float) -> str:
        """
        Format percentage change with + or - sign.
        
        Args:
            change_percent: Percentage change (positive or negative)
            
        Returns:
            Formatted percentage string (e.g., "+1.18%" or "-2.34%")
        """
        sign = "+" if change_percent >= 0 else ""
        return f"{sign}{change_percent:.2f}%"
    
    def fetch_stocks_data(self) -> List[Dict[str, Any]]:
        """
        Fetch stock data for all configured symbols with aligned formatting.
        
        Returns:
            List of dictionaries with stock data for each symbol
        """
        if not self.symbols:
            return []
        
        # First pass: fetch all stock data
        # Use a list with None placeholders to maintain index alignment
        raw_results = [None] * len(self.symbols)
        yfinance_period = self._map_time_window_to_yfinance(self.time_window)
        
        for index, symbol in enumerate(self.symbols):
            try:
                stock_data = self._fetch_single_stock(symbol, yfinance_period)
                if stock_data:
                    raw_results[index] = stock_data
            except Exception as e:
                logger.error(f"Error fetching stock data for {symbol}: {e}")
                # Keep None placeholder to maintain index alignment
        
        # Filter out None entries for alignment calculation, but keep track of indices
        valid_stocks = [s for s in raw_results if s is not None]
        
        if not valid_stocks:
            return []
        
        # Calculate max widths for alignment (only from valid stocks)
        max_price_width = 0
        max_percent_width = 0
        
        for stock in valid_stocks:
            current_price_str = self._format_price(stock["current_price"])
            change_percent_str = self._format_percentage(stock["change_percent"])
            
            # Price width includes "$" and space: "$ 1234.56" = 8 chars
            price_width = len(f"${current_price_str}")
            max_price_width = max(max_price_width, price_width)
            
            # Percentage width: "+12.34%" = 7 chars
            percent_width = len(change_percent_str)
            max_percent_width = max(max_percent_width, percent_width)
        
        # Second pass: apply aligned formatting and maintain index alignment
        # Ensure we process ALL indices, even if some stocks failed
        results = []
        for index in range(len(self.symbols)):
            if index < len(raw_results) and raw_results[index] is not None:
                stock = raw_results[index]
                current_price_str = self._format_price(stock["current_price"])
                change_percent_str = self._format_percentage(stock["change_percent"])
                
                # Right-align price and percentage
                price_aligned = f"${current_price_str}".rjust(max_price_width)
                percent_aligned = change_percent_str.rjust(max_percent_width)
                
                # Rebuild formatted string with aligned values
                color_tile = stock.get("color_tile", "{white}")
                symbol = stock["symbol"]
                formatted = f"{symbol}{color_tile} {price_aligned} {percent_aligned}"
                
                # Update stock data with aligned formatted string
                stock["formatted"] = formatted
                results.append(stock)
            else:
                # Create placeholder entry for failed stock to maintain index alignment
                symbol = self.symbols[index] if index < len(self.symbols) else f"UNKNOWN_{index}"
                results.append({
                    "symbol": symbol,
                    "current_price": 0.0,
                    "previous_price": 0.0,
                    "change_percent": 0.0,
                    "change_direction": "none",
                    "formatted": f"{symbol}{{white}} $0.00 +0.00%",
                    "color_tile": "{white}",
                    "company_name": f"Failed to fetch: {symbol}",
                })
        
        return results
    
    def _fetch_single_stock(self, symbol: str, period: str) -> Optional[Dict[str, Any]]:
        """
        Fetch data for a single stock symbol.
        
        Args:
            symbol: Stock symbol (e.g., "GOOG")
            period: yfinance period string (e.g., "1d", "max")
            
        Returns:
            Dictionary with stock data, or None if failed
        """
        try:
            ticker = yf.Ticker(symbol)
            
            # Get current price (latest available)
            info = ticker.info
            current_price = info.get("regularMarketPrice") or info.get("currentPrice")
            
            if current_price is None:
                logger.warning(f"No current price available for {symbol}")
                return None
            
            # For "1d" period, we want yesterday's close, not today's open
            # For other periods, use the first close in the historical data
            if period == "1d":
                # Get 5 days of data to ensure we have yesterday's close
                hist = ticker.history(period="5d")
            else:
                # Get historical data for comparison
                hist = ticker.history(period=period)
            
            if hist.empty:
                logger.warning(f"No historical data available for {symbol} with period {period}")
                return None
            
            # Get previous price
            if period == "1d":
                # For daily changes, use yesterday's close (second-to-last day)
                if len(hist) >= 2:
                    previous_price = float(hist.iloc[-2]["Close"])
                else:
                    # Fallback to first price if not enough history
                    previous_price = float(hist.iloc[0]["Close"])
            else:
                # For other periods, use first price in the period
                previous_price = float(hist.iloc[0]["Close"])
            
            current_price = float(current_price)
            
            # Calculate percentage change
            if previous_price > 0:
                change_percent = ((current_price - previous_price) / previous_price) * 100
            else:
                change_percent = 0.0
            
            # Determine direction
            change_direction = "up" if change_percent >= 0 else "down"
            
            # Format values
            current_price_str = self._format_price(current_price)
            previous_price_str = self._format_price(previous_price)
            change_percent_str = self._format_percentage(change_percent)
            
            # Determine color based on percentage change
            if change_percent > 0:
                color_tile = "{green}"
            elif change_percent < 0:
                color_tile = "{red}"
            else:
                color_tile = "{white}"
            
            # Create initial formatted display string (will be realigned in fetch_stocks_data)
            # Format: <SYMBOL><COLOR> $<CURRENT_PRICE> <PERCENTAGE_CHANGE_SIGN><PERCENTAGE_CHANGE>
            # Note: No parentheses around percentage to save 2 tiles for prices > $1000
            formatted = f"{symbol}{color_tile} ${current_price_str} {change_percent_str}"
            
            # Get company name if available
            company_name = info.get("longName") or info.get("shortName") or symbol
            
            return {
                "symbol": symbol,
                "current_price": current_price,
                "previous_price": previous_price,
                "change_percent": change_percent,  # Raw number (positive or negative)
                "change_direction": change_direction,
                "formatted": formatted,  # Will be updated with alignment in fetch_stocks_data
                "color_tile": color_tile,  # Store color_tile for alignment step
                "company_name": company_name,
            }
            
        except Exception as e:
            logger.error(f"Error fetching stock data for {symbol}: {e}", exc_info=True)
            return None
    
    @staticmethod
    def validate_symbol(symbol: str) -> Dict[str, Any]:
        """
        Validate if a stock symbol is valid using yfinance.
        
        Args:
            symbol: Stock symbol to validate
            
        Returns:
            Dictionary with validation result:
            {
                "valid": bool,
                "symbol": str,
                "name": str (if valid),
                "error": str (if invalid)
            }
        """
        if not symbol or not symbol.strip():
            return {
                "valid": False,
                "symbol": symbol,
                "error": "Empty symbol"
            }
        
        symbol = symbol.strip().upper()
        
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # Check if we got valid data (invalid symbols return empty info or error)
            if not info or "symbol" not in info:
                return {
                    "valid": False,
                    "symbol": symbol,
                    "error": "Symbol not found"
                }
            
            # Try to get price to confirm it's valid
            current_price = info.get("regularMarketPrice") or info.get("currentPrice")
            if current_price is None:
                return {
                    "valid": False,
                    "symbol": symbol,
                    "error": "No price data available"
                }
            
            # Get company name
            company_name = info.get("longName") or info.get("shortName") or symbol
            
            return {
                "valid": True,
                "symbol": symbol,
                "name": company_name
            }
            
        except Exception as e:
            logger.debug(f"Symbol validation failed for {symbol}: {e}")
            return {
                "valid": False,
                "symbol": symbol,
                "error": str(e)
            }
    
    @staticmethod
    def search_symbols(query: str, limit: int = 10, finnhub_api_key: Optional[str] = None) -> List[Dict[str, str]]:
        """
        Search for stock symbols by query.
        
        Uses Finnhub API if key is provided, otherwise searches curated list.
        
        Args:
            query: Search query (symbol or company name)
            limit: Maximum number of results
            finnhub_api_key: Optional Finnhub API key
            
        Returns:
            List of dictionaries with symbol and name:
            [{"symbol": "GOOG", "name": "Alphabet Inc."}, ...]
        """
        query = query.strip().upper()
        if not query:
            return []
        
        results = []
        
        # Try Finnhub API if key is provided
        if finnhub_api_key:
            try:
                import finnhub
                # finnhub-python package uses Client class
                finnhub_client = finnhub.Client(api_key=finnhub_api_key)
                search_results = finnhub_client.symbol_lookup(query)
                
                if search_results and "result" in search_results:
                    for item in search_results["result"][:limit]:
                        # Filter to US stocks only (type == "Common Stock" and exchange in US exchanges)
                        if item.get("type") == "Common Stock":
                            symbol = item.get("symbol", "")
                            description = item.get("description", "")
                            if symbol and description:
                                results.append({
                                    "symbol": symbol,
                                    "name": description
                                })
                
                if results:
                    return results[:limit]
            except Exception as e:
                logger.debug(f"Finnhub search failed, falling back to curated list: {e}")
        
        # Fall back to curated list search
        query_lower = query.lower()
        for stock in POPULAR_STOCKS:
            if len(results) >= limit:
                break
            
            symbol = stock["symbol"]
            name = stock["name"]
            
            # Match if query is in symbol or name (case-insensitive)
            if query_lower in symbol.lower() or query_lower in name.lower():
                results.append({
                    "symbol": symbol,
                    "name": name
                })
        
        return results[:limit]


# Singleton instance
_stocks_source: Optional[StocksSource] = None


def get_stocks_source() -> Optional[StocksSource]:
    """Get or create the stocks source singleton."""
    global _stocks_source
    from ..config import Config
    
    if not Config.STOCKS_ENABLED:
        return None
    
    if _stocks_source is None:
        _stocks_source = StocksSource(
            symbols=Config.STOCKS_SYMBOLS,
            time_window=Config.STOCKS_TIME_WINDOW,
            finnhub_api_key=Config.FINNHUB_API_KEY if Config.FINNHUB_API_KEY else None
        )
    
    return _stocks_source


def reset_stocks_source() -> None:
    """Reset the stocks source singleton."""
    global _stocks_source
    _stocks_source = None

