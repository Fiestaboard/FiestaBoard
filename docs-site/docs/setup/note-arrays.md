---
sidebar_position: 6
description: "Set up a Vestaboard Note array in FiestaBoard — via the Cloud API with a single token, or entirely on your local network with per-Note IPs and keys."
keywords:
  [
    Vestaboard Note array,
    note array setup,
    local array mode,
    X-Vestaboard-Token,
    local API,
    multi-board,
    split-flap wall,
  ]
---

# Note Array Setup

A **Note array** is several Vestaboard Notes tiled together into one larger
display. FiestaBoard treats the whole array as a single canvas, so your pages,
plugins, and schedules render across it just like they would on a Flagship or
a single Note.

Each Note is 15 × 3 characters, so an array's size is
`(notes wide × 15) × (notes tall × 3)` — up to the 8 × 8 maximum
(120 × 24 characters).

Arrays can be driven two ways:

| | Cloud mode | Local Array Mode |
|---|---|---|
| Credentials | One `X-Vestaboard-Token` | Each Note's IP + Local API key |
| Network | Internet + Vestaboard Cloud | Your LAN only — private |
| Rate limit | 1 message / 15 seconds | None |
| Transition animations | Not available | Supported |
| Subscription | Vestaboard Cloud API | None |

## Add the board

In the FiestaBoard web UI, open **Settings → Hardware**, click **Add Board**,
and choose **Note Array**. The new board starts as a *2 side-by-side* array in
Cloud mode. Pick your size with the **Board type** dropdown — five presets
(2 side-by-side, 4 side-by-side, 2 stacked, 4 stacked, 2×2 grid) plus
**Custom…** for anything up to 8 × 8 Notes.

## Cloud mode

1. Keep the connection on **Cloud API**.
2. Paste your `X-Vestaboard-Token` (from your Vestaboard Cloud API
   subscription — this is **not** the Read/Write key) into the
   **Cloud API Token** field.
3. Optionally click **Auto-detect from board** to read the array's size over
   the Cloud API instead of picking it by hand.

## Local Array Mode

In local mode FiestaBoard slices each rendered frame into 15 × 3 pieces and
sends every Note its own slice directly over your network — no cloud
round-trip, no rate limit, and transitions work.

### 1. Switch the connection to Local API

In the board's **Connection** section, select **Local API**. The token field
is replaced by the **Board tiles** grid: one slot per Note, laid out like your
wall. (Auto-detect is hidden in local mode — the array's size is defined by
the tiles you assign.)

### 2. Assign each slot

Click a slot to open its assignment dialog:

- **Scan network for boards** lists Vestaboards found on your network — click
  one to fill in its IP. Boards already assigned to another slot are labeled.
- Or type the Note's **IP address** (and port, default `7000`) by hand.
- Enter the Note's **Local API key** — or switch to **Enablement Token** and
  exchange it for a key. Each Note has its own key.
- **Test** checks that FiestaBoard can reach that Note; **Save tile** stores
  the assignment.

A partially assigned array still works — assigned Notes show their slice,
unassigned slots stay dark. The badge above the grid tracks progress.

### 3. Verify with Identify

**Identify** works like your computer's monitor-arrangement screen: it flashes
a slot's position number on the physical board it points at (per-slot, before
or after saving, or **Identify all** at once). The pattern clears
automatically on the next update cycle.

### 4. Rearrange with Move

If Identify reveals boards in the wrong order, open either slot and use
**Move to position** — choosing an empty slot relocates the tile, choosing an
occupied one swaps the two. Each board keeps its own IP and key; nothing to
retype. The whole flow is keyboard-accessible: arrow keys move between slots,
Enter opens a slot, and Move is a standard select.

## Good to know

- **Resizing keeps your keys.** Shrink a 2×2 to 2×1 and back — the hidden
  tiles' IPs and keys are preserved and reappear.
- **Local mode: Notes flip independently.** Tiles may start flipping a moment
  apart; FiestaBoard sends them the same transition to keep the skew small.
- **Cloud mode: one send every 15 seconds.** FiestaBoard throttles
  automatically; very fast page rotations may not all reach the board.

## Troubleshooting

**Some Notes update and others don't (local mode).** Open the stale slots'
dialogs and hit **Test** — an unreachable Note usually means a changed IP
(give your Notes DHCP reservations) or a wrong key. Failed tiles are retried
automatically on the next update cycle.

**Two Notes show swapped content (local mode).** Their slots point at each
other's IPs. **Identify all**, then swap them with **Move to position**.

**The board doesn't update (cloud mode).** Check the **Cloud API Token** is
set and your Vestaboard Cloud API subscription is active, and remember the
15-second rate limit.

## See also

- [Local development](./local-development.md) — run FiestaBoard with the
  bundled mock boards to try arrays without hardware.
- The in-repo
  [Note Arrays reference](https://github.com/Fiestaboard/FiestaBoard/blob/main/docs/reference/NOTE_ARRAYS.md)
  — dimensions model, transports, and endpoints for contributors.
