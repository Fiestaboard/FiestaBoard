"""Stock Prices plugin for FiestaBoard.

Displays real-time stock prices using Yahoo Finance.
"""

from typing import Any, Dict, List, Optional
import logging

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

# Time window mapping
TIME_WINDOW_MAP = {
    "1 Day": "1d",
    "5 Days": "5d",
    "1 Month": "1mo",
    "3 Months": "3mo",
    "6 Months": "6mo",
    "1 Year": "1y",
    "2 Years": "2y",
    "5 Years": "5y",
    "ALL": "max",
}


class StocksPlugin(PluginBase):
    """Stock prices plugin.
    
    Fetches real-time stock data from Yahoo Finance via yfinance.
    """
    
    def __init__(self, manifest: Dict[str, Any]):
        """Initialize the stocks plugin."""
        super().__init__(manifest)
        self._cache: Optional[Dict[str, Any]] = None
    
    @property
    def plugin_id(self) -> str:
        return "stocks"
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate stocks configuration."""
        errors = []
        
        symbols = config.get("symbols", [])
        if not symbols:
            errors.append("At least one stock symbol is required")
        elif len(symbols) > 5:
            errors.append("Maximum 5 stock symbols allowed")
        
        time_window = config.get("time_window", "1 Day")
        if time_window not in TIME_WINDOW_MAP:
            errors.append(f"Invalid time window: {time_window}")
        
        return errors
    
    def fetch_data(self) -> PluginResult:
        """Fetch stock data for all configured symbols."""
        try:
            import yfinance as yf
        except ImportError:
            return PluginResult(
                available=False,
                error="yfinance library not installed"
            )
        
        symbols = self.config.get("symbols", [])
        if not symbols:
            return PluginResult(
                available=False,
                error="No stock symbols configured"
            )
        
        time_window = self.config.get("time_window", "1 Day")
        period = TIME_WINDOW_MAP.get(time_window, "1d")
        
        try:
            stocks_data = []
            
            for symbol in symbols[:5]:
                stock_data = self._fetch_single_stock(symbol, period)
                if stock_data:
                    stocks_data.append(stock_data)
            
            if not stocks_data:
                return PluginResult(
                    available=False,
                    error="Failed to fetch any stock data"
                )
            
            # Align formatting across all stocks
            stocks_data = self._align_formatting(stocks_data)
            
            # Primary stock (first one)
            primary = stocks_data[0]
            
            data = {
                # Primary stock fields
                "symbol": primary["symbol"],
                "current_price": primary["current_price"],
                "previous_price": primary["previous_price"],
                "change_percent": primary["change_percent"],
                "change_direction": primary["change_direction"],
                "formatted": primary["formatted"],
                "company_name": primary["company_name"],
                # Aggregate
                "symbol_count": len(stocks_data),
                # Array of all stocks
                "stocks": stocks_data,
            }
            
            self._cache = data
            return PluginResult(available=True, data=data)
            
        except Exception as e:
            logger.exception("Error fetching stock data")
            return PluginResult(available=False, error=str(e))
    
    def _fetch_single_stock(self, symbol: str, period: str) -> Optional[Dict]:
        """Fetch data for a single stock."""
        import yfinance as yf
        
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            current_price = info.get("regularMarketPrice") or info.get("currentPrice")
            if current_price is None:
                return None
            
            # Get historical data for comparison
            if period == "1d":
                hist = ticker.history(period="5d")
            else:
                hist = ticker.history(period=period)
            
            if hist.empty:
                return None
            
            # Calculate previous price
            if period == "1d" and len(hist) >= 2:
                previous_price = float(hist.iloc[-2]["Close"])
            else:
                previous_price = float(hist.iloc[0]["Close"])
            
            current_price = float(current_price)
            
            # Calculate change
            if previous_price > 0:
                change_percent = ((current_price - previous_price) / previous_price) * 100
            else:
                change_percent = 0.0
            
            change_direction = "up" if change_percent >= 0 else "down"
            
            # Determine color
            if change_percent > 0:
                color_tile = "{66}"  # green
            elif change_percent < 0:
                color_tile = "{63}"  # red
            else:
                color_tile = "{69}"  # white
            
            company_name = info.get("longName") or info.get("shortName") or symbol
            
            return {
                "symbol": symbol.upper(),
                "current_price": current_price,
                "previous_price": previous_price,
                "change_percent": round(change_percent, 2),
                "change_direction": change_direction,
                "color_tile": color_tile,
                "company_name": company_name,
                "formatted": "",  # Will be set in alignment step
            }
            
        except Exception as e:
            logger.error(f"Error fetching stock {symbol}: {e}")
            return None
    
    def _align_formatting(self, stocks: List[Dict]) -> List[Dict]:
        """Align price and percentage formatting across all stocks."""
        if not stocks:
            return stocks
        
        # Calculate max widths
        max_price_width = 0
        max_percent_width = 0
        
        for stock in stocks:
            price_str = f"${stock['current_price']:.2f}"
            percent_str = f"{'+' if stock['change_percent'] >= 0 else ''}{stock['change_percent']:.2f}%"
            max_price_width = max(max_price_width, len(price_str))
            max_percent_width = max(max_percent_width, len(percent_str))
        
        # Apply aligned formatting
        for stock in stocks:
            price_str = f"${stock['current_price']:.2f}".rjust(max_price_width)
            sign = "+" if stock['change_percent'] >= 0 else ""
            percent_str = f"{sign}{stock['change_percent']:.2f}%".rjust(max_percent_width)
            stock["formatted"] = f"{stock['symbol']}{stock['color_tile']} {price_str} {percent_str}"
        
        return stocks
    
    def get_formatted_display(self) -> Optional[List[str]]:
        """Return default formatted stocks display."""
        if not self._cache:
            result = self.fetch_data()
            if not result.available:
                return None
        
        data = self._cache
        if not data:
            return None
        
        stocks = data.get("stocks", [])
        lines = ["STOCKS".center(22), ""]
        
        for stock in stocks[:4]:
            lines.append(stock["formatted"][:22])
        
        while len(lines) < 6:
            lines.append("")
        
        return lines[:6]


# Export the plugin class
Plugin = StocksPlugin

