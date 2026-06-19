# Note Array setup

A **Note array** is several Vestaboard Notes tiled together into one larger
display. FiestaBoard treats the whole array as a single canvas, so your pages,
plugins, and schedules render across it just like they would on a Flagship or a
single Note.

This page walks through connecting a Note array, picking its size, and getting
your Cloud API token.

> **Where to get your token:** Note arrays talk to the **Vestaboard Cloud API**
> using an `X-Vestaboard-Token`. You get this token from your Vestaboard Cloud
> API subscription — it is **not** the Read/Write key used by single Flagship
> and Note boards.

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
- A **Vestaboard Cloud API subscription** and its `X-Vestaboard-Token`.
- A running FiestaBoard instance you can reach in a browser.

## Quick setup

### 1. Add the board

In the FiestaBoard web UI, open **Settings → Display** and add a board (or edit
an existing one).

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
| 2 × 2 grid        | 2 × 2         | 30 × 6             |

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

### 5. View it

Save your changes. FiestaBoard renders your active page across the full array.
Open the page editor or preview to confirm the layout looks right at the new
size.

## Good to know

- **No transition animations.** The Cloud API used by Note arrays sends a full
  frame at once; FiestaBoard skips transition strategies for these boards.
- **One send every 15 seconds.** Note-array sends are rate-limited to at least
  15 seconds apart. FiestaBoard throttles automatically — rapid changes are
  coalesced rather than rejected — but very fast page rotations may not all
  reach the board.

## Troubleshooting

**"Could not detect the board configuration."**
The array returned no layout, or a size FiestaBoard can't classify. Confirm the
token is correct and the board is reachable, then set the size manually with the
**Board type** dropdown instead of Auto-detect.

**The board doesn't update.**
Note arrays only send through the Cloud API. Make sure the **Cloud API Token**
field is set (it shows a masked placeholder when saved) and that your Vestaboard
Cloud API subscription is active. Sends are also rate-limited to one every 15
seconds — see [Good to know](#good-to-know).

**The layout looks cut off or wrong.**
Check that **Notes wide** and **Notes tall** match your physical hardware. The
displayed size (for example `30 × 6`) is `width × height` in characters.

## See also

- [Note Arrays reference](../reference/NOTE_ARRAYS.md) — the dimensions model,
  the presets, custom sizing, and the auto-detect endpoint for contributors.
