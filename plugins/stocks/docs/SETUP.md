# Stocks Monitoring Setup Guide

The Stocks feature lets you monitor up to 5 stock symbols with real-time prices, percentage changes, and automatic color coding. Perfect for keeping tabs on your portfolio or market indices.

## Overview

**What it does:**
- Track up to 5 stock symbols simultaneously
- Display current prices and percentage changes
- Automatic color coding (green=up, red=down, white=unchanged)
- Configurable time windows (1 Day, 1 Month, 1 Year, etc.)
- Symbol search with autocomplete
- Column-aligned formatting for clean display

**Use Cases:**
- Monitor your portfolio at a glance
- Track major indices (S&P 500, Nasdaq, Dow)
- Watch specific stocks you're interested in
- Compare performance across different time windows

## Prerequisites

- ✅ No API key required for basic functionality (uses Yahoo Finance)
- ✅ Optional: Finnhub API key for enhanced symbol search
- ✅ Valid stock symbols (e.g., AAPL, GOOG, MSFT)

## Quick Setup

### 1. Enable Stocks Monitoring

Via Web UI (Recommended):
1. Go to the **Integrations** page
2. Find **Stocks** section
3. Toggle the **Stocks** plugin on
4. Click **Save Changes**

Via Environment Variables:
```bash
# Add to .env
STOCKS_ENABLED=true
STOCKS_SYMBOLS=GOOG,AAPL,MSFT,TSLA,NVDA  # Up to 5 symbols
STOCKS_TIME_WINDOW=1 Day  # Default comparison period
STOCKS_REFRESH_SECONDS=300  # Optional: refresh interval (default: 5 minutes)
```

### 2. Add Stock Symbols

Via Web UI (Recommended):
1. Go to the **Stocks** plugin on the **Integrations** page
2. Use the **Symbol Search** to find stocks:
   - Type symbol or company name (e.g., "AAPL" or "Apple")
   - Autocomplete suggestions appear
   - Click to add symbol
3. Add up to 5 symbols
4. **Save** your configuration

Via Environment Variables:
```bash
# Comma-separated list (max 5)
STOCKS_SYMBOLS=GOOG,AAPL,MSFT,TSLA,NVDA
```

### 3. Choose Time Window

Select the period for percentage change calculation:

Via Web UI:
1. In the **Stocks** plugin on the **Integrations** page
2. Select **Time Window** from dropdown:
   - 1 Day (default)
   - 5 Days
   - 1 Month
   - 3 Months
   - 6 Months
   - 1 Year
   - 2 Years
   - 5 Years
   - ALL (since inception)
3. **Save**

Via Environment Variables:
```bash
STOCKS_TIME_WINDOW=1 Day
```

### 4. (Optional) Add Finnhub API Key

For enhanced symbol search and autocomplete:

1. Get free API key from [finnhub.io](https://finnhub.io/)
2. Sign up for free account
3. Copy your API key
4. Add to Settings or `.env`:

```bash
FINNHUB_API_KEY=your_finnhub_api_key_here
```

**Note:** Finnhub is optional. Without it, you get basic symbol search with popular stocks.

### 5. Create a Page to Display Stocks

1. Go to **Pages** and click **New**
2. Choose **Template** page type
3. Add your template using stock variables:

**Example Template:**
```
{center}STOCK PRICES
{stocks.stocks.0.formatted}
{stocks.stocks.1.formatted}
{stocks.stocks.2.formatted}
{stocks.stocks.3.formatted}
{stocks.stocks.4.formatted}
```

4. **Save** and **Set as Active**

## Template Variables

### Pre-Formatted Display

Easiest way to display stocks with automatic formatting:

```
{stocks.stocks.0.formatted}
# Example output: "GOOG{green} $150.25 +1.18%"
```

The `formatted` variable includes:
- Symbol
- Color code based on change (green/red/white)
- Current price with $ sign
- Percentage change with +/- sign

### Individual Stock Variables

Access specific stocks using index (0-4):

```
{stocks.stocks.0.symbol}          # Symbol (e.g., "GOOG")
{stocks.stocks.0.current_price}   # Current price (e.g., "150.25")
{stocks.stocks.0.change_percent}  # Percentage change (e.g., "+1.18%")
{stocks.stocks.0.change_direction} # Change direction (e.g., "up"/"down")
{stocks.stocks.0.formatted}       # Pre-formatted line with color
```

### Metadata

```
{stocks.symbol_count}             # Number of configured stocks
```

## Example Templates

![Stock Prices Display](./stocks-display.png)

### Simple List

```
{center}MY PORTFOLIO
{stocks.stocks.0.formatted}
{stocks.stocks.1.formatted}
{stocks.stocks.2.formatted}
{stocks.stocks.3.formatted}
{stocks.stocks.4.formatted}
```

Output example:
```
     MY PORTFOLIO
GOOG{green} $150.25 +1.18%
AAPL{green} $185.30 +0.52%
MSFT{red} $378.90 -0.35%
TSLA{green} $242.15 +2.87%
NVDA{green} $495.20 +1.95%
```

### With Header

```
{center}TECH STOCKS
{stocks.stocks.0.formatted}
{stocks.stocks.1.formatted}
{stocks.stocks.2.formatted}
```

### Compact Format

```
{center}STOCKS
{stocks.stocks.0.symbol}: {stocks.stocks.0.current_price} ({stocks.stocks.0.change_percent})
{stocks.stocks.1.symbol}: {stocks.stocks.1.current_price} ({stocks.stocks.1.change_percent})
{stocks.stocks.2.symbol}: {stocks.stocks.2.current_price} ({stocks.stocks.2.change_percent})
```

### Major Indices

```
{center}MARKET INDICES
{stocks.stocks.0.formatted}
{stocks.stocks.1.formatted}
{stocks.stocks.2.formatted}
```

With symbols: `^GSPC` (S&P 500), `^IXIC` (Nasdaq), `^DJI` (Dow Jones)

### Custom Formatting

```
{center}PORTFOLIO VALUE
{stocks.stocks.0.symbol|pad:6}${stocks.stocks.0.current_price|pad:8}{stocks.stocks.0.change_percent|pad:8}
{stocks.stocks.1.symbol|pad:6}${stocks.stocks.1.current_price|pad:8}{stocks.stocks.1.change_percent|pad:8}
```

## Configuration Reference

### Environment Variables

```bash
# Required
STOCKS_ENABLED=true

# Stock symbols (comma-separated, max 5)
STOCKS_SYMBOLS=GOOG,AAPL,MSFT,TSLA,NVDA

# Time window for percentage change
STOCKS_TIME_WINDOW=1 Day  # Options: 1 Day, 5 Days, 1 Month, 3 Months, 
                          #          6 Months, 1 Year, 2 Years, 5 Years, ALL

# Refresh interval (seconds)
STOCKS_REFRESH_SECONDS=300  # Default: 300 (5 minutes)

# Optional: Enhanced symbol search
FINNHUB_API_KEY=your_finnhub_api_key_here
```

### config.json Format

```json
{
  "features": {
    "stocks": {
      "enabled": true,
      "symbols": ["GOOG", "AAPL", "MSFT", "TSLA", "NVDA"],
      "time_window": "1 Day",
      "refresh_seconds": 300,
      "finnhub_api_key": "your_finnhub_key"
    }
  }
}
```

## Symbol Selection Guide

### Popular Stock Categories

**Tech Giants (FAANG+)**
- AAPL (Apple)
- MSFT (Microsoft)
- GOOG / GOOGL (Alphabet)
- AMZN (Amazon)
- META (Meta/Facebook)
- NVDA (NVIDIA)
- TSLA (Tesla)

**Market Indices**
- ^GSPC (S&P 500)
- ^IXIC (Nasdaq Composite)
- ^DJI (Dow Jones Industrial Average)
- ^RUT (Russell 2000)

**Financial**
- JPM (JPMorgan Chase)
- BAC (Bank of America)
- WFC (Wells Fargo)
- GS (Goldman Sachs)

**Consumer**
- WMT (Walmart)
- TGT (Target)
- COST (Costco)
- HD (Home Depot)

**ETFs**
- SPY (S&P 500 ETF)
- QQQ (Nasdaq 100 ETF)
- VOO (Vanguard S&P 500 ETF)
- VTI (Total Stock Market ETF)

### Symbol Format

- **US Stocks**: Use ticker symbol (e.g., AAPL, MSFT)
- **Indices**: Use ^prefix (e.g., ^GSPC, ^IXIC)
- **ETFs**: Use ticker symbol (e.g., SPY, QQQ)
- **International**: Some supported (e.g., TSM, BABA)

## Time Window Selection

Choose based on your investment horizon:

**Day Trading / Active**
- **1 Day**: See today's performance
- **5 Days**: Week's trend

**Short-term Investing**
- **1 Month**: Monthly performance
- **3 Months**: Quarterly results

**Long-term Investing**
- **6 Months**: Semi-annual trend
- **1 Year**: Annual performance
- **2 Years / 5 Years**: Long-term trends
- **ALL**: Since you started tracking

**Recommendation:** Start with **1 Day** for daily changes, switch to **1 Year** for long-term perspective.

## Color Coding Explained

Automatic color coding based on price change:

- 🟢 **Green** (`color_code: 66`): Positive change (price up)
- 🔴 **Red** (`color_code: 63`): Negative change (price down)
- ⚪ **White** (`color_code: 69`): No change (0.00%)

Colors are applied automatically in the `formatted` variable.

## Tips and Best Practices

### Choosing Stocks

1. **Limit to 5**: Display constraint, choose wisely
2. **Mix categories**: Blend indices, individual stocks, ETFs
3. **Track what matters**: Your actual holdings or interests
4. **Consider market hours**: Prices update during market hours (9:30am-4pm ET)

### Refresh Interval

- **300 seconds (5 min)**: Default, good for most uses
- **60 seconds (1 min)**: Day trading, very active monitoring
- **600 seconds (10 min)**: Less frequent checks, reduce API calls
- **1800 seconds (30 min)**: Casual monitoring

**Note:** Yahoo Finance rate limits are generous, but don't refresh too frequently.

### Market Hours

- **During market hours** (9:30am-4pm ET): Live price updates
- **After hours** (4pm-9:30am ET): Shows previous close
- **Weekends**: Shows Friday's closing price
- **Holidays**: No trading, shows last trading day

### Display Layout

The `formatted` variable provides column-aligned output:
```
GOOG  $150.25  +1.18%
AAPL  $185.30  +0.52%
MSFT  $378.90  -0.35%
```

Prices and percentages are automatically aligned.

## Troubleshooting

### Symbol Not Found

**Problem:** "Invalid symbol" or empty data

**Solutions:**
1. **Verify symbol**: Check on Yahoo Finance (finance.yahoo.com)
2. **Try variations**: Some companies have Class A/B shares (GOOG vs GOOGL)
3. **Check exchange**: Some international stocks not supported
4. **Use search**: Use symbol search in UI to find correct symbol

### Prices Not Updating

**Problem:** Prices seem stale

**Solutions:**
1. **Check market hours**: Markets may be closed
2. **Verify refresh interval**: Check STOCKS_REFRESH_SECONDS
3. **Check logs**: Look for Yahoo Finance API errors
4. **Test directly**: 
   ```bash
   curl http://localhost:4420/api/displays/stocks
   ```
5. **Restart service**: May need container restart

### Color Coding Wrong

**Problem:** Green/red colors don't match expectations

**Solutions:**
1. **Check time window**: Colors based on selected time window, not just today
2. **Verify data**: Check `change_percent` value matches color
3. **Market timing**: Pre-market/after-hours can affect colors
4. **Clear cache**: Stop/start service to refresh

### Finnhub Search Not Working

**Problem:** Enhanced search not showing results

**Solutions:**
1. **Verify API key**: Check Finnhub key is correct
2. **Check rate limits**: Free tier has limits
3. **Test API directly**:
   ```bash
   curl "https://finnhub.io/api/v1/search?q=Apple&token=YOUR_KEY"
   ```
4. **Use basic search**: Works without Finnhub, just fewer results

### Five Symbol Limit

**Problem:** Need to track more than 5 stocks

**Solutions:**
1. **Create multiple pages**: Different pages for different portfolios
2. **Rotate symbols**: Change symbols periodically
3. **Use indices**: Track broad market with ^GSPC, ^IXIC instead of individual stocks
4. **Prioritize**: Focus on most important holdings

## Data Source

Stocks uses **Yahoo Finance (yfinance)**:

- **API**: Unofficial Yahoo Finance API via yfinance Python library
- **Coverage**: Most US and major international stocks
- **Update Frequency**: Real-time during market hours (with ~15min delay for free tier)
- **Rate Limits**: Generous, hundreds of requests per minute
- **Historical Data**: Available for all time windows

**Optional:** Finnhub API for enhanced symbol search
- **API**: https://finnhub.io/
- **Free Tier**: 60 calls/minute
- **Purpose**: Better autocomplete and company search

## Advanced Usage

### Combining with Other Features

```
{center}MORNING BRIEF
STOCKS
{stocks.stocks.0.formatted}
{stocks.stocks.1.formatted}

COMMUTE: {muni.stops.0.formatted}
WEATHER: {weather.temperature}° {weather.condition}
```

### Portfolio Performance

```
{center}PORTFOLIO
TECH
{stocks.stocks.0.formatted}
{stocks.stocks.1.formatted}

INDICES
{stocks.stocks.2.formatted}
{stocks.stocks.3.formatted}
```

### Custom Color Logic

```python
# In custom template logic (advanced)
if stocks.stocks.0.change_percent > 2:
    # Major gain, add extra visual
    message += "🚀"
```

## API Reference

### REST API Endpoints

```bash
# Search for stock symbols
GET /stocks/search?query=Apple&limit=10

# Validate a symbol
POST /stocks/validate
Body: {"symbol": "AAPL"}

# Get formatted stock display
GET /displays/stocks

# Get raw stock data
GET /displays/stocks/raw
```

## Related Features

- **Weather**: Complete morning dashboard with stocks + weather
- **DateTime**: Add current time to stock display
- **Traffic**: Morning commute overview with portfolio check

## Resources

- [Yahoo Finance](https://finance.yahoo.com/)
- [Finnhub Stock API](https://finnhub.io/)
- [yfinance Library](https://pypi.org/project/yfinance/)
- [Stock Symbol Lookup](https://finance.yahoo.com/lookup)

---

**Next Steps:**
1. Enable Stocks in Settings
2. Add your favorite symbols (up to 5)
3. Choose your time window
4. Create a page with stock prices
5. Set as active page or combine with other data

