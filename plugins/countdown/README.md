# Countdown Plugin

Display the remaining time to an event in real time on your board.

![Countdown Display](./docs/board-display.png)

**→ [Setup Guide](./docs/SETUP.md)**

## Overview

The Countdown plugin shows the remaining days, hours, minutes, and seconds until a target date/time. Values recompute on every board refresh — useful for the last day of school, a wedding, a product launch, or any date you want to watch tick down.

## Template Variables

### Event Info

| Variable | Description | Example |
|----------|-------------|---------|
| `{{countdown.event_name}}` | Name of the event | `Last Day of School` |
| `{{countdown.target_datetime}}` | Target datetime string | `2027-01-01T00:00:00` |
| `{{countdown.is_expired}}` | `true` if the event has passed, `false` otherwise | `false` |

### Countdown Values

| Variable | Description | Example |
|----------|-------------|---------|
| `{{countdown.days}}` | Remaining days | `22` |
| `{{countdown.hours}}` | Remaining hours (0–23) | `3` |
| `{{countdown.minutes}}` | Remaining minutes (0–59) | `10` |
| `{{countdown.seconds}}` | Remaining seconds (0–59) | `45` |
| `{{countdown.total_seconds}}` | Total remaining seconds | `1911045` |
| `{{countdown.formatted}}` | Pre-formatted string | `22D 3H 10M` |

## Example Templates

### Classic Countdown (Inspired by Vestaboard)

```jinja
{center}COUNTDOWN UNTIL
{{countdown.event_name}}

{{countdown.days}} DAYS
{{countdown.hours}} HOURS
{{countdown.minutes}} MINUTES
```

### Compact Countdown

```jinja
{center}{{countdown.event_name}}
{{countdown.days}}D {{countdown.hours}}H {{countdown.minutes}}M
```

### Days Only

```jinja
{center}{{countdown.days}} DAYS UNTIL
{{countdown.event_name}}
```

### Full Countdown with Seconds

```jinja
{center}{{countdown.event_name}}
{{countdown.days}}D {{countdown.hours}}H
{{countdown.minutes}}M {{countdown.seconds}}S
```

## Configuration

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| enabled | boolean | false | Enable/disable the plugin |
| event_name | string | "Event" | Name of the event to count down to |
| target_datetime | string | *(required)* | Target date/time in ISO format (e.g., `2027-01-01T00:00:00`) |
| timezone | string | "America/Los_Angeles" | IANA timezone name |

## Features

- **Real-time Countdown**: Days, hours, minutes, and seconds remaining
- **Timezone-aware**: Configurable timezone with autocomplete picker
- **Expired Detection**: Automatically detects when the event has passed
- **Flexible Formatting**: Use individual components or the pre-formatted string
- **No API Key Required**: Works out of the box with no external dependencies

## Author

FiestaBoard Team
