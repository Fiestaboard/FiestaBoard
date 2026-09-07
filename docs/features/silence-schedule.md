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

<AppShot name="settings-silence-schedule" alt="Silence schedule settings in the Settings page" />

### Via the Web UI

1. Open the FiestaBoard Web UI at `http://localhost:4420`
2. Go to **Settings** → **Behavior**
3. Find the **Silence Schedule** section
4. Set your **Start Time** and **End Time**
5. Save your settings

Settings save automatically a second after you stop typing.

## Multiple Boards

Silence settings are **per board**. If you run a Flagship in the living room
and a Note on your desk, each keeps its own quiet hours, its own silence mode,
and its own silence page — the Flagship can go quiet at 10 PM while the Note
stays live, and each can show a page sized for its own display.

Pick the board you want with the board selector in the sidebar, then edit the
Silence Schedule card; you are editing that board's settings.

A few things follow from this:

- **A board you have not configured inherits the install-wide schedule.** That
  is the schedule you had before you ever touched a second board, so upgrading
  changes nothing: every existing board keeps the quiet hours it already had.
  A board you add later starts out quiet during the same window rather than
  flipping at 3 AM.
- **The silence page picker only offers pages that fit that board.** A 22×6
  Flagship page cannot be chosen for a 15×3 Note.
- **Single-board installs see no difference.** There is just the one board, so
  its schedule is the schedule.
- **Manual sends respect the target board's window.** Sending a message or a
  page from the Web UI, the API, or Home Assistant is blocked while *that*
  board is silenced, so a 2 AM send cannot wake a board whose own quiet hours
  say it should be asleep.
- **The Home Assistant `silence_mode` sensor reports the primary board.** Like
  the other entities in that payload (active page, transition style), it
  describes the primary board rather than the install as a whole. The same is
  true of `GET /silence-status` when you do not name a board.

## How It Works

When the current time falls within the silence window, FiestaBoard chooses
how to handle the board based on the configured **silence mode**:

| Mode | Behaviour |
| --- | --- |
| **Show "SNOOZING" message** (default) | The board is set to a clean `SNOOZING` message sized for your device (Flagship or Note). No other content is overlaid. |
| **Leave board unchanged** | The board is left exactly as it was — no further updates are sent until silence ends. |
| **Show a specific page** | A page you choose is rendered once when silence begins and frozen on the board. Template variables are not refreshed until silence ends. |

The mode is chosen per board, and so is the page: the silence page is always
rendered at the size of the board it is being sent to.

Regardless of which mode you pick:

- The display service stops sending refresh updates to that board while it is silenced
- The web UI and API continue to function normally
- Scheduled pages are skipped during that board's silence hours

When the silence window ends:

- The display service resumes normal operation
- The currently scheduled (or default) page is sent to the board

:::tip
The silence schedule uses your configured timezone (`TIMEZONE` in `.env`). Make sure this is set correctly for your location.
:::

## Example Configurations

| Goal | Start Time | End Time |
| --- | --- | --- |
| Nighttime quiet hours | `22:00` (10 PM) | `07:00` (7 AM) |
| Quiet outside office hours | `18:00` (6 PM) | `08:00` (8 AM) |

:::caution
`SILENCE_SCHEDULE_START_TIME` and `SILENCE_SCHEDULE_END_TIME` appear in
`env.example`, but the display service does not read them — they are written
to a config key nothing consumes. Set your quiet hours in the Web UI (or via
`PUT /settings/silence-schedule`) instead.
:::

## Next Steps

- [Schedule Mode](/docs/features/schedule) - Set up time-based page rotation
- [Environment Variables](/docs/reference/environment-variables) - All configuration options
