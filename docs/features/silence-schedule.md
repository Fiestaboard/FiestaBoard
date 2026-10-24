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
5. Optionally enable **Show held messages when silence ends** (off by default).

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
- **Manual changes respect the target board's window.** Picking a page saves
  the selection for later. Message sends and Live Output leave a silenced
  board quiet unless you explicitly choose to send now. Pausing the board
  prevents writes even when you override silence.
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
- A held message is attempted first, if you enabled holding and one is pending
- Otherwise, the selected manual page or current scheduled/default page is shown
- A paused or offline board keeps its held message for a later attempt

:::tip
The silence schedule uses your configured timezone (`TIMEZONE` in `.env`). Make sure this is set correctly for your location.
:::

## Manual Changes During Silence

Home shows **Silenced until…** throughout the active window, with the ending
time in your browser's time zone and selected UI language. Selecting a page
saves it for when silence ends; the page picker and confirmation explain this.
**Show now** explicitly sends the selected saved page during silence. It sends
the full page freshly rendered, never the shortened held-message preview.
Pause still prevents the write.

Compose and Force Set warn before waking the primary board. These two actions
keep their existing temporary-override behavior: Compose creates an indefinite
one-off message; Force Set shows a page for the chosen duration and then
returns to the schedule. In multi-board installs, Compose names the primary
board when it differs from the board selected in the sidebar. Opening either
dialog checks quiet hours again. If that check is pending or unavailable, an
explicit wake warning remains visible. Even outside known quiet hours, the
dialog explains that sending now can wake the board during quiet hours; this
remains true if the dialog stays open when quiet hours begin.

Live Output continues updating the editor preview while leaving a silenced
board quiet. **Send to board anyway** explicitly allows writes for that Live
Output session. **Stop sending**, turning Live Output off, or changing the
output board ends that permission. The permission warning and **Stop sending**
stay visible even when quiet-hours status is unavailable or stale. Pause still
prevents writes. A paused render never claims to have
updated the board.

## Holding a Message for Later

**Show held messages when silence ends** is an opt-in setting for each board;
boards without an override inherit the install-wide value. It applies in all
three silence modes. Turning it on lets accepted manual sends wait quietly
until silence ends. Compose offers **Hold until…** beside **Send now anyway**.
With holding off, a blocked message is refused rather than saved.

Each board has one persistent held-message slot. A newer accepted message
replaces the older one for that board. Home shows a shortened preview and
**Discard message** clears only the selected board's slot. Discard does not
change your saved active page, and cannot undo a hardware send that already
started. **Show now** sends your selected page, which may differ from the held
message; it is not a held-message replay button.

Held messages survive restarts and expire after 24 hours. Pages and plugin
displays render fresh at delivery; text uses the target board's normal v9
wrapping and dimensions. Delivery waits for silence to end, the board to be
resumed, and hardware output to be available. Failed or throttled attempts
retain the message for a later attempt. A successful explicit send supersedes
an older held message; a failed or paused send keeps it.

Home keeps the held preview and **Discard message** visible after quiet hours
end or silence is disabled, including while the board is paused or offline.
A saved page that is deleted, cannot render, or no longer fits the board stays
pending without blocking other normal content or a new explicit override.

If the queue cannot be saved, a hold or discard reports an error and leaves the
previous saved message intact. Before delivery, the queue records that a write
is starting. If delivery or its final cleanup cannot be confirmed, Home shows
**Delivery needs attention** and automatic retry stops to avoid repeating a
message after restart. This can also happen if the app stops after recording
the attempt but before sending. Discard the entry, or explicitly send new
content to replace it. **Show now** still sends the selected page. A failed
discard keeps the entry visible so you can try again after storage recovers.

## API Behavior

See the [API reference](/docs/reference/api-endpoints) for request and response
fields. For example, `POST /v1/boards/primary/message` with
`{"text":"GOOD MORNING"}` returns HTTP 202 with `held: true`, `silenced: true`,
`sent: false`, and `ends_at_utc` when holding is enabled during silence.
Otherwise a silenced message is refused with HTTP 409. Add the JSON boolean
`"override_silence": true` only when you deliberately want to wake the board.
`force` only sends unchanged content again; neither flag bypasses pause.

A page selection can succeed while returning `sent: false` (v1) or
`sent_to_board: false` (the UI endpoint): the choice was saved without a
hardware write. Live rendering likewise returns a preview while silenced.
`GET /silence-status?board_id=…` reports the ending instant, holding setting,
and optional held summary; `DELETE /silence-queue?board_id=…` discards that
board's held intent. Omitting the board id targets the primary board.

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
