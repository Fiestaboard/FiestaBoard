---
sidebar_position: 24
description: "Count down to any event in real time on your split-flap display with FiestaBoard. No API key required."
keywords: [FiestaBoard countdown, event countdown, days remaining, split-flap countdown, Vestaboard countdown timer]
---

# Countdown

Display the remaining days, hours, minutes, and seconds until any target date. **No API key required.**

## Overview

The Countdown plugin shows the remaining time until a target date and time you set:

- Days, hours, minutes, and seconds remaining
- Optional **Count Up (Days Since)** mode counts upward from a past date instead — anniversaries, "days since launch", streaks
- Automatically detects when the event has passed
- Timezone-aware — configure any IANA timezone
- Values update on every board refresh

## Setup

1. Open **http://localhost:4420**
2. Go to the **Integrations** page
3. Toggle **Countdown** on
4. Click **Configure** and set the event name, target date/time, and timezone
5. Optionally toggle **Count Up (Days Since)** to count upward from a past date. A target still in the future counts down until it arrives, then counts up
6. Click **Save Changes**

:::tip
Countdown requires no external service or API key. All values are computed locally.
:::

## Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{{countdown.event_name}}` | Configured event name | `Last Day of School` |
| `{{countdown.target_datetime}}` | Target datetime (ISO 8601) | `2027-01-01T00:00:00` |
| `{{countdown.days}}` | Whole days remaining (or elapsed in count-up mode) | `86` |
| `{{countdown.hours}}` | Hours remaining or elapsed (0–23) | `14` |
| `{{countdown.minutes}}` | Minutes remaining or elapsed (0–59) | `30` |
| `{{countdown.seconds}}` | Seconds remaining or elapsed (0–59) | `45` |
| `{{countdown.total_seconds}}` | Total seconds until (or since) the target | `7473045` |
| `{{countdown.formatted}}` | Pre-formatted summary | `86D 14H 30M` |
| `{{countdown.is_expired}}` | `"true"` once the target has passed | `false` |
| `{{countdown.is_count_up}}` | `"true"` when values are counting up (count-up mode, past target) | `false` |

## Example Templates

**Classic countdown:**

```jinja
{center}COUNTDOWN UNTIL
{{countdown.event_name}}

{{countdown.days}} DAYS
{{countdown.hours}} HOURS
{{countdown.minutes}} MINUTES
```

**Compact:**

```jinja
{center}{{countdown.event_name}}
{{countdown.days}}D {{countdown.hours}}H {{countdown.minutes}}M
```

**Days only:**

```jinja
{center}{{countdown.days}} DAYS UNTIL
{{countdown.event_name}}
```

**Days since (count-up mode):**

```jinja
{center}{{countdown.days}} DAYS SINCE
{{countdown.event_name}}
```

## Next Steps

- [Date & Time Plugin](/docs/plugins/date-time) -- Display the current date and time
- [Plugins Overview](/docs/plugins/overview) -- See all available plugins
