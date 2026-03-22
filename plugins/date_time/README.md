# Date & Time Plugin

Display current date and time on your board with comprehensive formatting options.

![Date & Time Display](./docs/board-display.png)

**→ [Setup Guide](./docs/SETUP.md)** - Configuration and setup instructions

## Overview

The Date & Time plugin provides various date and time variables that update automatically based on your configured timezone. It supports multiple time formats (12-hour and 24-hour), US date formats, and flexible month representations.

## Template Variables

### Time Variables

```
{{date_time.time}}          # 24-hour format (e.g., "14:30")
{{date_time.time_24h}}      # 24-hour format (e.g., "14:30")
{{date_time.time_12h}}      # 12-hour format with AM/PM (e.g., "2:30 PM")
{{date_time.hour}}         # Hour 0-23 (e.g., "14")
{{date_time.minute}}       # Minute 00-59 (e.g., "30")
```

### Date Variables

```
{{date_time.date}}          # ISO format (e.g., "2025-01-15")
{{date_time.date_us}}       # US format MM/DD/YYYY (e.g., "01/15/2025")
{{date_time.date_us_short}} # US format MM/DD/YY (e.g., "01/15/25")
{{date_time.datetime}}      # Full datetime (e.g., "2025-01-15 14:30")
```

### Day Variables

```
{{date_time.day_of_week}}   # Full day name (e.g., "Wednesday")
{{date_time.day}}           # Day of month 1-31 (e.g., "15")
```

### Month Variables

```
{{date_time.month}}              # Full month name (e.g., "January")
{{date_time.month_abbr}}         # 3-letter abbreviation (e.g., "Jan")
{{date_time.month_number}}        # Month number 1-12 (e.g., "1")
{{date_time.month_number_padded}} # Month number 01-12 (e.g., "01")
```

### Year Variables

```
{{date_time.year}}          # Year (e.g., "2025")
```

### Timezone Variables

```
{{date_time.timezone}}      # Full timezone name (e.g., "America/Los_Angeles")
{{date_time.timezone_abbr}} # Timezone abbreviation (e.g., "PST")
```

## Example Templates

### Simple 24-Hour Clock

```
{center}{{date_time.time_24h}}
```

### Simple 12-Hour Clock

```
{center}{{date_time.time_12h}}
```

### Full Date Display

```
{center}{{date_time.day_of_week}}
{{date_time.date}}
{{date_time.time_12h}}
```

### US Date Format

```
{center}{{date_time.date_us}}
{{date_time.time_12h}} {{date_time.timezone_abbr}}
```

### Classic Format

```
{center}{{date_time.month}} {{date_time.day}}, {{date_time.year}}
{{date_time.time_12h}} {{date_time.timezone_abbr}}
```

### Compact Format

```
{center}{{date_time.month_abbr}} {{date_time.day}}
{{date_time.time_12h}}
```

### Date Components

```
{center}{{date_time.month_number_padded}}/{{date_time.day}}/{{date_time.year}}
{{date_time.day_of_week}}
```

## Configuration

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| enabled | boolean | true | Enable/disable the plugin |
| timezone | string | "America/Los_Angeles" | IANA timezone name |

## Timezone Examples

- `America/Los_Angeles` - Pacific Time
- `America/New_York` - Eastern Time
- `America/Chicago` - Central Time
- `Europe/London` - UK Time
- `Asia/Tokyo` - Japan Time

## Features

- **Multiple Time Formats**: 12-hour (with AM/PM) and 24-hour formats
- **US Date Formats**: MM/DD/YYYY and MM/DD/YY formats
- **Flexible Month Display**: Full name, abbreviation, or numeric (padded/unpadded)
- **Timezone Support**: Configurable timezone with autocomplete picker
- **Real-time Updates**: Automatically updates based on configured refresh interval
- **No API Key Required**: Works out of the box with no external dependencies

## Author

FiestaBoard Team

