---
sidebar_position: 3
description: "Set quiet hours on your FiestaBoard to silence split-flap display updates during nighttime or specific periods."
keywords: [FiestaBoard silence schedule, quiet hours, do not disturb, night mode, split-flap quiet, Vestaboard silence]
---

# Silence Schedule

The silence schedule feature lets you set quiet hours for your board, preventing any updates during specified time periods. This is useful for nighttime hours or any time you don't want the board making noise.

## Overview

Split-flap displays can be noisy when updating. The silence schedule ensures your board stays quiet during hours when you don't want it flipping characters, like when you're sleeping.

## Configuring Silence Hours

<ThemedScreenshot src="/img/guides/settings-silence-schedule.png" alt="Silence schedule settings in the Settings page" />

### Via the Web UI

1. Open the FiestaBoard Web UI at `http://localhost:4420`
2. Go to **Settings**
3. Find the **Silence Schedule** section
4. Set your **Start Time** and **End Time**
5. Save your settings

### Via Environment Variables

You can also configure silence hours in your `.env` file:

```bash
# Silence Schedule
SILENCE_SCHEDULE_START_TIME=22:00    # 10:00 PM
SILENCE_SCHEDULE_END_TIME=07:00      # 7:00 AM
```

## How It Works

When the current time falls within the silence window:

- The display service **stops sending updates** to the board
- The board remains on whatever was last displayed
- The web UI and API continue to function normally
- Scheduled pages are skipped during silence hours

When the silence window ends:

- The display service resumes normal operation
- The currently scheduled (or default) page is sent to the board

:::tip
The silence schedule uses your configured timezone (`TIMEZONE` in `.env`). Make sure this is set correctly for your location.
:::

## Example Configurations

### Nighttime Quiet Hours

```bash
SILENCE_SCHEDULE_START_TIME=22:00    # Board goes quiet at 10 PM
SILENCE_SCHEDULE_END_TIME=07:00      # Board resumes at 7 AM
```

### Office Hours Only

```bash
SILENCE_SCHEDULE_START_TIME=18:00    # Quiet after 6 PM
SILENCE_SCHEDULE_END_TIME=08:00      # Resume at 8 AM
```

## Next Steps

- [Schedule Mode](/docs/features/schedule) - Set up time-based page rotation
- [Environment Variables](/docs/reference/environment-variables) - All configuration options
