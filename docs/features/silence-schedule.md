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
2. Go to **Displays** and open the display you want to configure
3. Select **Playback** and find **Silence Schedule**
4. Set your **Start Time** and **End Time**
5. Save your settings

Settings save automatically a second after you stop typing.

## Multiple Boards

Silence settings are **per board**. If you run a Flagship in the living room
and a Note on your desk, each keeps its own quiet hours, its own silence mode,
and its own silence page — the Flagship can go quiet at 10 PM while the Note
stays live, and each can show a page sized for its own display.

Open the display's **Playback** tab and edit its Silence Schedule card. These
controls always apply to the display whose detail page is open, even if the
sidebar selects another board. The app-wide Settings page has no Scheduling tab;
old scheduling links redirect to the selected display.

A few things follow from this:

- **Existing boards retain their quiet hours when upgrading.** A newly added
  board starts with silence disabled and its own independent settings. Set its
  quiet hours from its Playback tab; it does not inherit another board's window.
- **The silence page picker only offers pages that fit that board.** A 22×6
  Flagship page cannot be chosen for a 15×3 Note.
- **Single-board installs see no difference.** There is just the one board, so
  its schedule is the schedule.
- **Manual sends respect the target board's window.** Sending a message or a
  page from the Web UI, the API, or Home Assistant leaves *that* board alone
  while it is silenced, so a 2 AM send cannot wake a board whose own quiet
  hours say it should be asleep. See
  [Changing the board during silence](#changing-the-board-during-silence) for
  what happens to the send instead.
- **The "Another app changed this board" notice waits too.** While a board is
  silenced, FiestaBoard leaves it alone on purpose, so the notice and its
  Restore and Save as page buttons are hidden until silence ends. See
  [Saving what another app put on the board](/docs/features/page-editor#saving-what-another-app-put-on-the-board).
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

### When the silence window ends

On the first update after the window ends, in this order:

1. If the board is **holding a message** (see
   [Show held messages when silence ends](#show-held-messages-when-silence-ends)),
   that message is shown first. It stays up until the page's content next
   changes, like any message you send by hand.
2. Otherwise the board shows what it would show at that moment: the page you
   picked (including one you picked *during* silence), or your schedule's
   current page.

A board that is paused when the window ends stays paused, and a held message
for it is dropped rather than kept for whenever you resume it. The same goes
for an install whose output is set to the web UI only.

## Changing the board during silence

A silenced board never changes because of something you did in the app, the
API, Home Assistant or an AI assistant, unless you explicitly say **Show now**.

- **Picking a page** (Home, Change Page) saves your choice and leaves the board
  alone. Home shows a *Silenced until 7:00 AM* alert that says what happens
  when silence ends, and the toast after you pick a page carries a **Show now**
  button.
- **Show now** is the explicit override: the alert on Home and the toast both
  have it. It writes the page to the board right away.
- **Force Set** and **Compose** deliberately beat silence. During silence both
  dialogs say so, and their confirm buttons read **Show now anyway** and
  **Send now anyway**, so waking the board is always a named choice.
- **Live Output** in the page editor keeps previewing while the board is
  silenced, but does not write to it. **Send to board anyway** turns writing on
  until you stop it or turn Live Output off.
- **Pause wins.** A paused board is never written, whatever you pass.

### Over the API

Every write surface takes the same flag, `override_silence` (default `false`):

| Surface | Without the flag, during silence | With `override_silence: true` |
| --- | --- | --- |
| `PUT /v1/boards/{board}/active-page`, `PUT /settings/active-page` | The page is saved; `sent: false`, `silenced: true` and a `reason` that says when it will show | Saved and shown now |
| `POST /v1/boards/{board}/message`, `POST /send-message` | `202` with `held: true` when the board holds messages, else `409` | Written now |
| `POST /pages/{id}/send`, `POST /displays/{type}/send` (query param) | Not written; `silenced: true` (and `held: true` when held) | Written now |
| `POST /templates/render/live` | Rendered but not written; `silenced: true` | Written now |
| MCP `set_active_page`, `send_message` | The result says `silenced` / `held` and when silence ends | Written now |
| MQTT `send_message` JSON payload, e.g. `{"message": "HI", "override_silence": true}` | Held or dropped | Written now |

`force` on `POST /v1/boards/{board}/message` keeps its own meaning (write even
when the board already shows that exact content); it does not override
silence.

On `POST /pages/{id}/send` and `POST /displays/{type}/send`, the beta-only
`?force=true` from v10.0.0-beta.26 still overrides silence as a deprecated
alias of `override_silence`. Switch to `override_silence`; the alias goes away
in a later release.

## Show held messages when silence ends

Turn on **Show held messages when silence ends** in **Displays → your board → Playback →
Silence Schedule** (per board, like the rest of the schedule; the API key is
`show_queued_on_exit`). With it on, a message sent to the board during silence
is **held** instead of refused, and shown the moment silence ends:

- **What is held:** messages from Compose (**Hold until 7:00 AM**),
  `POST /v1/boards/{board}/message`, `POST /send-message`, the MCP
  `send_message` tool, Home Assistant's MQTT `send_message`, and page and
  display sends. A page or plugin display is rendered fresh when it is shown,
  so the morning gets the morning's data.
- **Newest wins:** one held message per board; sending another replaces it.
- **Text is word-wrapped** to the board when it is shown.
- **It survives a restart** and is kept for at most 24 hours.
- **You can see and discard it.** Home shows the held message under the
  silence alert with a **Discard message** button
  (`DELETE /silence-queue?board_id=…` over the API). `GET /silence-status`
  reports it as `held`, and `holds_blocked_sends` says whether the option is
  on.
- **An explicit "show now" write wins.** Anything you write with
  `override_silence` replaces the held message.

With the option off, a message sent during silence is refused (`409`), as
before. Page picks never need this option: they are always saved and shown when
silence ends.

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
