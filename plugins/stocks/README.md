# Stock Prices Plugin

![Stock Prices Display](./docs/stocks-display.png)

Display real-time stock prices and percentage changes.

**→ [Setup Guide](./docs/SETUP.md)** - Configuration and optional API key setup

## Overview

The Stock Prices plugin fetches live stock data from Yahoo Finance and displays prices with color-coded percentage changes.

## Features

- Track up to 5 stock symbols
- Real-time price updates
- Percentage change from configurable time windows
- Color-coded indicators (green/red)
- Optional Finnhub API for enhanced symbol search

## Template Variables

### Primary Stock (First Symbol)

```
{{stocks.symbol}}           # Symbol (e.g., "GOOG")
{{stocks.current_price}}    # Current price (e.g., "150.25")
{{stocks.change_percent}}   # Percentage change (e.g., "+1.18")
{{stocks.change_direction}} # "up" or "down"
{{stocks.formatted}}        # Pre-formatted line
{{stocks.company_name}}     # Company name
{{stocks.symbol_count}}     # Number of tracked symbols
```

### Individual Stocks (Array)

```
{{stocks.stocks.0.symbol}}          # First stock symbol
{{stocks.stocks.0.current_price}}   # First stock price
{{stocks.stocks.0.change_percent}}  # First stock change
{{stocks.stocks.0.formatted}}       # First stock formatted

{{stocks.stocks.1.symbol}}          # Second stock symbol
{{stocks.stocks.1.formatted}}       # Second stock formatted
```

## Example Templates

### Single Stock

```
{center}{{stocks.symbol}}
${{stocks.current_price}}
{{stocks.change_percent}}%
```

### Multiple Stocks

```
{center}STOCKS
{{stocks.stocks.0.formatted}}
{{stocks.stocks.1.formatted}}
{{stocks.stocks.2.formatted}}
{{stocks.stocks.3.formatted}}
```

### Compact View

```
{center}MARKET
{{stocks.stocks.0.symbol}}: ${{stocks.stocks.0.current_price}}
{{stocks.stocks.1.symbol}}: ${{stocks.stocks.1.current_price}}
```

## Configuration

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| enabled | boolean | false | Enable/disable the plugin |
| symbols | array | - | Stock symbols to track (max 5) |
| time_window | string | "1 Day" | Period for change calculation |
| finnhub_api_key | string | - | Optional API key for symbol search |
| refresh_seconds | integer | 300 | Update interval |

### Time Windows

- 1 Day - Daily change
- 5 Days - Weekly change
- 1 Month - Monthly change
- 3 Months - Quarterly change
- 6 Months - Half-year change
- 1 Year - Annual change
- ALL - All-time change

## Symbol Search

The plugin supports symbol search. With a Finnhub API key, search is more comprehensive. Without it, a curated list of popular US stocks is used.

Get a free Finnhub API key at [finnhub.io](https://finnhub.io/).

## Author

FiestaBoard Team

