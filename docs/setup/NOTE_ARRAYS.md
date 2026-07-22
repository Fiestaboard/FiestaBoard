# Note Array setup

A **Note array** is several Vestaboard Notes tiled together into one larger
display. FiestaBoard treats the whole array as a single canvas, so your pages,
plugins, and schedules render across it just like they would on a Flagship or a
single Note.

This page walks through connecting a Note array and picking its size. Arrays
can be driven two ways:

- **Cloud mode** — one `X-Vestaboard-Token`; Vestaboard's cloud fans the frame
  out to your Notes.
- **Local mode** — FiestaBoard talks to each Note directly over your own
  network. Every Note gets its own IP address and Local API key, and you place
  each one into its slot in the array grid. No cloud subscription required.

> **Where to get your Cloud token:** in cloud mode, Note arrays talk to the
> **Vestaboard Cloud API** using an `X-Vestaboard-Token`. You get this token
> from your Vestaboard Cloud API subscription — it is **not** the Read/Write
> key used by single Flagship and Note boards. In local mode you instead need
> each Note's **Local API key** (via its enablement token).

## Overview

Each Note is 15 × 3 characters. An array is a grid of Notes, so its size in
characters is:

```text
width  = notes wide × 15
height = notes tall × 3
```

Sizes are described as **width × height** throughout the app (for example a
4-wide array is `60 × 3`).

You'll need:

- A Vestaboard Note array (two or more Notes configured as a single board).
- **Cloud mode:** a Vestaboard Cloud API subscription and its
  `X-Vestaboard-Token` — or **local mode:** each Note's IP address and Local
  API key on your network.
- A running FiestaBoard instance you can reach in a browser.

## Quick setup

### 1. Add the board

In the FiestaBoard web UI, open **Settings → Hardware**, click **Add Board**,
and choose **Note Array**. The new board starts as a *2 side-by-side* array in
Cloud mode — adjust the size in the next step if yours differs. (You can also
convert an existing board with the **Board type** dropdown.)

> New arrays start in **Cloud API** mode. To drive the array over your own
> network instead, switch the connection to **Local API** and follow
> [Local mode](#local-mode-drive-each-note-directly) below.

### 2. Choose the board type and size

Open the **Board type** dropdown. It is grouped into:

- **Devices** — Flagship and Note (single boards).
- **Note arrays** — the five presets below, plus **Custom…**.

Pick a preset that matches your hardware:

| Board type        | Notes (W × H) | Characters (W × H) |
|-------------------|---------------|--------------------|
| 2 side-by-side    | 2 × 1         | 30 × 3             |
| 4 side-by-side    | 4 × 1         | 60 × 3             |
| 2 stacked         | 1 × 2         | 15 × 6             |
| 4 stacked         | 1 × 4         | 15 × 12            |
| 2×2 grid          | 2 × 2         | 30 × 6             |

If your array isn't one of the presets, choose **Custom…** and set **Notes
wide** and **Notes tall** (each from 1 to 8). For example, `3 × 2` Notes gives a
`45 × 6` canvas.

### 3. Paste the Cloud API token

With a Note-array size selected, a **Cloud API Token** field appears. Paste your
`X-Vestaboard-Token` here. Once saved, the field shows a masked placeholder to
confirm the token is set.

### 4. (Optional) Auto-detect instead

If you'd rather not look up your array's size by hand, click **Auto-detect from
board**. FiestaBoard reads the array's current layout over the Cloud API and
fills in the board type and size for you. (You still need the token saved first,
since the read uses it.)

> Auto-detect applies to **cloud** arrays and single boards. A local-mode
> array's size is defined by the tiles you assign, so there is nothing to
> detect — the button is not shown in local mode.

### 5. View it

Save your changes. FiestaBoard renders your active page across the full array.
Open the page editor or preview to confirm the layout looks right at the new
size.

## Local mode: drive each Note directly

In local mode FiestaBoard slices the rendered frame into 15 × 3 pieces and
sends each piece straight to its Note over your network — no cloud round-trip,
no 15-second rate limit, and transition animations work.

### 1. Switch the connection to Local API

In the board's **Connection** section, select **Local API**. The Cloud token
field is replaced by the **Board tiles** grid: one slot per Note, laid out
exactly like your wall.

### 2. Assign each slot

Click a slot to open its assignment dialog:

- **Scan network for boards** lists Vestaboards found on your network — click
  one to fill in its IP. Boards already assigned to another slot are labeled.
- Or type the Note's **IP address** (and port, default `7000`) by hand.
- Enter the Note's **Local API key** — or switch to **Enablement Token** and
  click **Get API Key from Board** to exchange the token for a key. Each Note
  has its own key.
- **Test** checks that FiestaBoard can reach that Note.
- **Save tile** stores the assignment.

Repeat for every slot. The badge above the grid tracks progress (for example
`1/4 tiles assigned`). A partially assigned array still works — assigned Notes
show their slice, unassigned slots stay dark.

### 3. Verify the layout with Identify

With several identical Notes on a wall, it's easy to wire the right IP to the
wrong position. **Identify** works like your computer's monitor-arrangement
screen:

- **Identify** (in a slot's dialog) flashes that slot's position number on the
  physical board it points at — before or after saving.
- **Identify all** sends every configured Note its position number at once, so
  you can read the numbering off the wall left-to-right, top-to-bottom.

The identify pattern clears automatically on the next update cycle (within the
polling interval). If the board is paused, the pattern stays until you resume.

If two boards are swapped, open either slot, point it at the other IP (rescan
or edit the host), and save.

## Good to know

- **Cloud mode: no transition animations.** The Cloud API sends a full frame at
  once; FiestaBoard skips transition strategies for cloud-driven arrays. In
  **local mode** transitions work — each Note animates its own slice.
- **Cloud mode: one send every 15 seconds.** Cloud note-array sends are
  rate-limited to at least 15 seconds apart. FiestaBoard throttles
  automatically — rapid changes are coalesced rather than rejected — but very
  fast page rotations may not all reach the board. Local mode has no such
  limit.
- **Local mode: Notes flip independently.** Each Note is its own device, so
  tiles may start flipping a moment apart. FiestaBoard sends them the same
  transition to keep the skew small.
- **Resizing keeps your keys.** If you shrink the array (say 2×2 → 2×1) the
  hidden tiles' IPs and keys are kept, and reappear when you grow it back.

## Troubleshooting

**"Could not detect the board configuration."**
The array returned no layout, or a size FiestaBoard can't classify. Confirm the
token is correct and the board is reachable, then set the size manually with the
**Board type** dropdown instead of Auto-detect.

**The board doesn't update (cloud mode).**
Make sure the **Cloud API Token** field is set (it shows a masked placeholder
when saved) and that your Vestaboard Cloud API subscription is active. Sends
are also rate-limited to one every 15 seconds — see
[Good to know](#good-to-know).

**Some Notes update and others don't (local mode).**
Open the stale slots' dialogs and hit **Test** — an unreachable Note usually
means a changed IP (give your Notes DHCP reservations) or a wrong key. A tile
that fails mid-send is retried automatically on the next update cycle; the
Notes that succeeded aren't re-sent.

**Two Notes show swapped content (local mode).**
Their slots point at each other's IPs. Use **Identify all** to see which board
answers for which position, then reassign the two slots.

**The layout looks cut off or wrong.**
Check that **Notes wide** and **Notes tall** match your physical hardware. The
displayed size (for example `30 × 6`) is `width × height` in characters.

## See also

- [Note Arrays reference](../reference/NOTE_ARRAYS.md) — the dimensions model,
  the presets, custom sizing, and the auto-detect endpoint for contributors.
