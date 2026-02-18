# Countdown Plugin Setup Guide

The Countdown plugin displays the remaining time until a target event on your board. It counts down in days, hours, minutes, and seconds.

## Overview

**What it does:**
- Counts down to a specific date and time
- Displays remaining days, hours, minutes, and seconds
- Automatically detects when the event has passed
- Supports configurable timezone

**Prerequisites:**
- ✅ None - works out of the box!

## Quick Setup

### 1. Enable the Plugin

In the FiestaBoard web UI:
1. Go to **Integrations**
2. Find **Countdown** and toggle it **On**

### 2. Configure the Countdown

1. Go to **Integrations** → **Countdown**
2. Click the **Configure** button
3. Set the **Event Name** (e.g., "Last Day of School")
4. Set the **Target Date & Time** in ISO format (e.g., `2025-06-15T00:00:00`)
5. Optionally set the **Timezone** (defaults to America/Los_Angeles)
6. Click **Save**

### 3. Use in Templates

Available variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `{{countdown.event_name}}` | Event name | `Last Day of School` |
| `{{countdown.target_datetime}}` | Target datetime | `2025-06-15T00:00:00` |
| `{{countdown.days}}` | Remaining days | `22` |
| `{{countdown.hours}}` | Remaining hours (0-23) | `3` |
| `{{countdown.minutes}}` | Remaining minutes (0-59) | `10` |
| `{{countdown.seconds}}` | Remaining seconds (0-59) | `45` |
| `{{countdown.total_seconds}}` | Total remaining seconds | `1911045` |
| `{{countdown.is_expired}}` | Whether event has passed | `false` |
| `{{countdown.formatted}}` | Pre-formatted countdown | `22D 3H 10M` |

## Example Templates

### Classic Countdown

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

## Configuration Reference

| Setting | Type | Required | Default | Description |
|---------|------|----------|---------|-------------|
| `enabled` | boolean | No | false | Enable/disable the plugin |
| `event_name` | string | No | "Event" | Name of the event |
| `target_datetime` | string | Yes | — | Target date/time in ISO format |
| `timezone` | string | No | "America/Los_Angeles" | IANA timezone name |

### Environment Variables

You can also configure the plugin via environment variables:

```bash
COUNTDOWN_TARGET=2025-06-15T00:00:00
COUNTDOWN_EVENT_NAME=Last Day of School
TIMEZONE=America/Los_Angeles
```

## Troubleshooting

**Issue: Plugin shows "Not Available"**
- Ensure a target datetime is set
- Verify the datetime format is ISO 8601 (e.g., `2025-06-15T00:00:00`)

**Issue: Wrong countdown displayed**
- Check your timezone setting is correct
- Ensure the target datetime is in the future

**Issue: Shows "Event has passed"**
- The target datetime is in the past; update it to a future date/time
