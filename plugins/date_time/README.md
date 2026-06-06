# Date & Time Plugin

Display the current date and time on your board, with formats for every occasion.

![Date & Time Display](./docs/board-display.png)

**→ [Setup Guide](./docs/SETUP.md)**

## Overview

The Date & Time plugin exposes the current date and time in the timezone you configure. It offers 12-hour and 24-hour clocks, US and ISO date formats, individual date parts, and a spoken-English time expression you can put straight on the board.

## Template Variables

### Time

| Variable | Description | Example |
|----------|-------------|---------|
| `{{date_time.time}}` | 24-hour time (`HH:MM`) | `14:30` |
| `{{date_time.time_24h}}` | 24-hour time (explicit alias of `time`) | `14:30` |
| `{{date_time.time_12h}}` | 12-hour time with AM/PM | `2:30 PM` |
| `{{date_time.hour}}` | Hour, 0–23 | `14` |
| `{{date_time.minute}}` | Minute, 00–59 (zero-padded) | `30` |
| `{{date_time.timezone_abbr}}` | Timezone abbreviation | `PST` |
| `{{date_time.timezone}}` | Full IANA timezone name | `America/Los_Angeles` |

### Date

| Variable | Description | Example |
|----------|-------------|---------|
| `{{date_time.date}}` | ISO date (`YYYY-MM-DD`) | `2025-03-21` |
| `{{date_time.day_of_week}}` | Day name | `Friday` |
| `{{date_time.day_of_week_abbr}}` | Day name abbreviation | `Fri` |
| `{{date_time.day_of_week_num}}` | ISO day of week, 1-7 | `5` |
| `{{date_time.day_of_year}}` | Day of year, 1-366 | `47` |
| `{{date_time.day_of_year_padded}}` | Day of year, 001-366 | `047` |
| `{{date_time.day}}` | Day of month, 1–31 | `21` |
| `{{date_time.month}}` | Full month name | `March` |
| `{{date_time.month_abbr}}` | 3-letter month | `Mar` |
| `{{date_time.month_number}}` | Month, 1–12 | `3` |
| `{{date_time.month_number_padded}}` | Month, 01–12 | `03` |
| `{{date_time.week_of_year}}` | ISO week number, 1-53 | `5` |
| `{{date_time.week_of_year_padded}}` | ISO week number, 01-53 | `05` |
| `{{date_time.quarter}}` | Quarter number, 1-4 | `1` |
| `{{date_time.year}}` | 4-digit year | `2025` |

### Formatted

| Variable | Description | Example |
|----------|-------------|---------|
| `{{date_time.datetime}}` | Date + 24h time | `2025-03-21 14:30` |
| `{{date_time.date_us}}` | US date (`MM/DD/YYYY`) | `03/21/2025` |
| `{{date_time.date_us_short}}` | Short US date (`M/D/YY`) | `3/21/25` |
| `{{date_time.time_english}}` | Spoken English time expression | `IT'S A QUARTER PAST ONE IN THE AFTERNOON.` |

## Example Templates

### Simple 24-hour clock

```jinja
{center}{{date_time.time_24h}}
```

### Day, date, and time

```jinja
{center}{{date_time.day_of_week}}
{{date_time.date}}
{{date_time.time_12h}}
```

### US date format

```jinja
{center}{{date_time.date_us}}
{{date_time.time_12h}} {{date_time.timezone_abbr}}
```

### Classic format

```jinja
{center}{{date_time.month}} {{date_time.day}}, {{date_time.year}}
{{date_time.time_12h}} {{date_time.timezone_abbr}}
```

### Compact format

```jinja
{center}{{date_time.month_abbr}} {{date_time.day}}
{{date_time.time_12h}}
```

### Spoken English time

```jinja
{{date_time.time_english}}
```

## Configuration

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `enabled` | boolean | `true` | Enable or disable the plugin |
| `timezone` | string | `America/Los_Angeles` | IANA timezone name |

## Features

- 12-hour (with AM/PM) and 24-hour clocks
- ISO, US, and short US date formats
- Individual date parts: day, month (name, abbreviation, number, padded), year
- Spoken English time expression — for example, `IT'S A QUARTER PAST ONE IN THE AFTERNOON.`
- Timezone-aware with an autocomplete IANA picker in the UI
- No API key required

## Author

FiestaBoard Team
