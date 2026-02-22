# Countdown Plugin

Display the remaining time to an event in real time on your board.

![Countdown Plugin Display](./docs/board-display.png)

**→ [Setup Guide](./docs/SETUP.md)** - Configuration and setup instructions

## Overview

The Countdown plugin shows the remaining days, hours, minutes, and seconds until a target date/time. It automatically updates each time the board refreshes, making it ideal for counting down to events like the last day of school, a holiday, a product launch, or any important date.

## Template Variables

### Countdown Variables

```
{{countdown.event_name}}       # Name of the event (e.g., "Last Day of School")
{{countdown.target_datetime}}  # Target datetime string (e.g., "2025-06-15T00:00:00")
{{countdown.days}}             # Remaining days (e.g., "22")
{{countdown.hours}}            # Remaining hours (0-23) (e.g., "3")
{{countdown.minutes}}          # Remaining minutes (0-59) (e.g., "10")
{{countdown.seconds}}          # Remaining seconds (0-59) (e.g., "45")
{{countdown.total_seconds}}    # Total remaining seconds (e.g., "1911045")
{{countdown.is_expired}}       # "true" if the event has passed, "false" otherwise
{{countdown.formatted}}        # Pre-formatted string (e.g., "22D 3H 10M")
```

## Example Templates

### Classic Countdown (Inspired by Vestaboard)

```
{center}COUNTDOWN UNTIL
{{countdown.event_name}}

{{countdown.days}} DAYS
{{countdown.hours}} HOURS
{{countdown.minutes}} MINUTES
```

### Compact Countdown

```
{center}{{countdown.event_name}}
{{countdown.days}}D {{countdown.hours}}H {{countdown.minutes}}M
```

### Days Only

```
{center}{{countdown.days}} DAYS UNTIL
{{countdown.event_name}}
```

### Full Countdown with Seconds

```
{center}{{countdown.event_name}}
{{countdown.days}}D {{countdown.hours}}H
{{countdown.minutes}}M {{countdown.seconds}}S
```

## Configuration

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| enabled | boolean | false | Enable/disable the plugin |
| event_name | string | "Event" | Name of the event to count down to |
| target_datetime | string | *(required)* | Target date/time in ISO format (e.g., `2025-06-15T00:00:00`) |
| timezone | string | "America/Los_Angeles" | IANA timezone name |

## Features

- **Real-time Countdown**: Days, hours, minutes, and seconds remaining
- **Timezone-aware**: Configurable timezone with autocomplete picker
- **Expired Detection**: Automatically detects when the event has passed
- **Flexible Formatting**: Use individual components or the pre-formatted string
- **No API Key Required**: Works out of the box with no external dependencies

## Author

FiestaBoard Team
