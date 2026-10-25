---
sidebar_position: 6
description: "Read what a FiestaBoard board shows from any device in any language: the panel config and frame endpoints, character codes, the message string, rich cells with colors and icons, polling cadence, and a minimal viewer."
keywords: [FiestaBoard frame API, FiestaPanel API, board frames, panel frame endpoint, TV viewer, ESP32 display, rich cells, polling, character codes]
---

# Subscribing to Board Frames

Every FiestaBoard board keeps the last frame it showed. Any device that can make an HTTP request can read that frame and draw it: a TV browser, an ESP32 with a small screen, a terminal, a script. This is the **pull** way to put FiestaBoard on a display. No plugin, no install, and any language.

FiestaPanel, FiestaBoard's own TV viewer, is built on exactly these two endpoints. If you would rather FiestaBoard **push** frames to a device, write an [output plugin](/docs/development/output-plugins) instead. [Building on FiestaBoard](/docs/development/integrations-overview) compares the two.

## Before You Start

Frames are read through a **panel**. A panel is a named view of one board, with a short number for typing on a TV remote. Create one in **Displays → Add a display → FiestaPanel** (see [FiestaPanel](/docs/features/fiestapanel)), and note its number or id.

The examples below use `http://fiestaboard.local:4420`. Use your FiestaBoard's address.

## The Two Endpoints

Both are read-only, and both are **public**: they need no login and no token, even with [authentication](/docs/setup/authentication) turned on, because a TV browser cannot sign in. Every path is under `/api`.

| Endpoint | Returns | Poll it |
|----------|---------|---------|
| `GET /api/panel/{panel}` | The panel's settings and its board's size | Every 10 seconds, to pick up size and setting changes |
| `GET /api/panel/{panel}/frame` | What the board shows now | Every 2 seconds |

`{panel}` is any of:

- the panel's short number, such as `1`
- the panel's id
- `display`, the panel set as this FiestaPi's HDMI display

An unknown panel answers `404`.

### `GET /api/panel/{panel}`

```bash
curl http://fiestaboard.local:4420/api/panel/1
```

```json
{
  "id": "q3V9xY2kP0aB",
  "short_code": 1,
  "name": "Living Room TV",
  "board_id": "board_tv",
  "screen_diagonal_inches": 55.0,
  "screen_aspect_w": 16.0,
  "screen_aspect_h": 9.0,
  "animations_enabled": false,
  "device_type": "panel",
  "board_missing": false,
  "rows": 9,
  "cols": 30,
  "board_color": "black",
  "code62_glyph": "heart",
  "render_style": "split_flap",
  "device_model": "fiestapanel_split_flap",
  "device_model_spec": { "id": "fiestapanel_split_flap", "technology": "split_flap", "...": "..." }
}
```

The fields a viewer needs:

| Field | Use |
|-------|-----|
| `rows`, `cols` | The board's grid, in characters. Lay out a blank grid of this size before the first frame arrives. |
| `board_color` | `"black"` or `"white"`: the board face to imitate |
| `code62_glyph` | What character code 62 draws on this board: `"degree"` (°) or `"heart"` (♥) |
| `animations_enabled` | Whether the user wants a flip animation between frames |
| `board_missing` | `true` when the panel's board was deleted; show a notice instead of a grid |
| `render_style` | `"split_flap"` (the default) or `"led_matrix"`: how the user wants the TV to draw the board. Absent from older servers; read absent as `"split_flap"`. |
| `device_model`, `device_model_spec` | The FiestaUI device model for that style and its full document. Pass the document to FiestaUI's `DisplayPreview` to draw the board in that style. |

The response carries a few more panel settings that FiestaPanel uses, such as auto-dim. Ignore the ones you do not need.

### `GET /api/panel/{panel}/frame`

```bash
curl http://fiestaboard.local:4420/api/panel/1/frame
```

```json
{
  "characters": [
    [0, 8, 9, 0, 0, 65, 0],
    [0, 23, 15, 18, 12, 4, 0]
  ],
  "message": " HI  {65} \n WORLD ",
  "rows": 2,
  "cols": 7,
  "updated_at": "2026-10-03T17:42:05+00:00"
}
```

| Field | Meaning |
|-------|---------|
| `characters` | The frame: `rows` rows of `cols` character codes. `null` until anything has been sent to the board. |
| `message` | The same frame as text, one line per row, with color tiles written as `{63}` to `{71}` |
| `rows`, `cols` | The grid size. Reported even when `characters` is `null`, so a viewer can draw an empty board. |
| `updated_at` | When the frame was sent, in ISO 8601 UTC, or `null` |
| `cells` | Rich cells with colors and icons. Present **only** for a board whose output draws them. See [Rich cells](#rich-cells). |

Each code is a FiestaBoard [character code](/docs/reference/character-codes): `0` is a blank, `1`–`26` are A–Z, `27`–`36` are 1–9 and 0, `37`–`62` are punctuation, and `63`–`71` are the color tiles from the [Color Guide](/docs/reference/color-guide). Draw code 62 as the panel's `code62_glyph`.

If a board's size changes, a frame of the old size is never served: you get `characters: null` and the new `rows` and `cols` until the next frame is sent. Re-read the panel config when that happens.

### Rich cells

A board whose output can draw color and icons, such as an LED matrix, also reports its frame as **rich cells**: the frame as FiestaUI's `BoardToken` rows, one object per cell.

```json
"cells": [
  [
    { "type": "char", "value": "H", "color": "red" },
    { "type": "char", "value": "I", "color": "red" },
    { "type": "char", "value": " " },
    { "type": "color", "code": "65", "icon": "sun" },
    { "type": "char", "value": "O", "color": "black", "background": "white" },
    { "type": "char", "value": "K", "color": "black", "background": "white" }
  ]
]
```

| Key | Present | Meaning |
|-----|---------|---------|
| `type` | Always | `"char"` or `"color"` |
| `value` | `"char"` | One character |
| `code` | `"color"` | The color tile's code, `"63"` to `"71"` |
| `color` | When set | The text color, from a color span such as `{red:HI}` |
| `background` | When set | The cell's background, from a block span such as `{black/white:OK}` |
| `icon` | When set | The icon name, such as `sun`. The cell's `code` or `value` is what to draw if you have no icon for it. |

`cells` is additive. When a board has no rich cells, the key is absent and the response is exactly what it always was. `characters` and `message` are always there, so a viewer that only understands codes keeps working on every board.

## Polling

FiestaBoard does not push frames to a viewer. Poll:

- **The frame every 2 seconds.** That is what FiestaPanel does, and it keeps a TV within a couple of seconds of the board.
- **The panel config every 10 seconds.** Sizes and settings change rarely.

Redraw only when `updated_at` or `characters` changes. If a request fails, keep showing the last frame and try again on the next tick. FiestaPanel shows a small dot in the corner while it is offline.

Reading a frame is cheap: FiestaBoard serves it from memory and never contacts the board's device to answer.

## Compatibility

These endpoints are what every FiestaPanel TV in the field runs on, so they change only **additively**. Existing fields keep their names and meanings, and new information arrives as new fields, as `cells` did in FiestaBoard 10.0.0. Ignore fields you do not recognize.

## A Minimal Viewer

A complete terminal viewer in Python, standard library only. It prints the board whenever the frame changes:

```python
import json
import time
import urllib.request

BASE = "http://fiestaboard.local:4420/api/panel/1"


def get(path=""):
    with urllib.request.urlopen(BASE + path, timeout=5) as response:
        return json.load(response)


last = None
while True:
    try:
        frame = get("/frame")
    except OSError as exc:
        print(f"offline: {exc}")
    else:
        if frame["updated_at"] != last:
            last = frame["updated_at"]
            print(frame["message"] if frame["characters"] else "(nothing shown yet)")
            print("-" * frame["cols"])
    time.sleep(2)
```

### On a microcontroller

The same loop fits an ESP32 or a Raspberry Pi Pico W driving a small screen:

1. Join Wi-Fi, then read `/api/panel/{panel}` once for `rows`, `cols` and `code62_glyph`.
2. Every 2 seconds, read `/api/panel/{panel}/frame`.
3. Skip the redraw when `updated_at` has not changed.
4. Map each code to your display's font. Draw codes `63`–`71` as filled cells in the [board colors](/docs/reference/color-guide), and code `62` as the panel's `code62_glyph`.
5. If your screen can show color, use `cells` when it is present, and fall back to `characters` when it is not.

Parse only the fields you need: on a large panel the frame is a few kilobytes of JSON.

## Next Steps

- [FiestaPanel](/docs/features/fiestapanel) - Create panels and use FiestaBoard's own TV viewer
- [Character Codes](/docs/reference/character-codes) - Every character code
- [Writing an Output Plugin](/docs/development/output-plugins) - Push frames to a device instead
- [Building on FiestaBoard](/docs/development/integrations-overview) - Every way to build on FiestaBoard
