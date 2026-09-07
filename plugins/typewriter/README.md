# Typewriter Plugin

A transition plugin that reveals the target message left-to-right, character by character, like an old typewriter.

![Typewriter Display](./docs/board-display.png)

**→ [Setup Guide](./docs/SETUP.md)**

## Overview

Typewriter is a transition plugin -- it doesn't display its own content. Instead, when one page replaces another on the board, Typewriter animates the change by revealing the new content one tile at a time, sweeping left-to-right and top-to-bottom.

FiestaBoard draws each frame itself and sends it as an ordinary board update, so Typewriter works on any board connection. (The built-in strategies -- Wave, Edges to Center, and friends -- are Vestaboard Local API features and only animate on a local-API board.)

## Template Variables

None. Transition plugins don't expose template variables; they shape *how* a board update happens, not *what* it shows.

## Example Templates

Typewriter is never placed in a template. Turn on the **Transition Plugins** beta (Settings → Advanced → Beta Features), then pick Typewriter from the **Transition** dropdown in the page editor's toolbar to use it on one page, or from Settings → Behavior → Board Transitions to make it the default for every page. A page's own choice wins over the global default; "Use global default" clears it.

Pages store the choice as `transition_strategy = "plugin:typewriter"`.

## Configuration

| Setting               | Type    | Default | Description                                              |
| --------------------- | ------- | ------- | -------------------------------------------------------- |
| `chars_per_frame`     | integer | 1       | Tiles flipped per step (1-22). Larger = faster.          |
| `frame_interval_ms`   | integer | 120     | Pause between steps in milliseconds (0-2000).            |

## Features

- Smooth left-to-right reveal of the target grid
- Tunable speed: choose how many tiles per step and how long between steps
- Works on any board connection, Local API or Cloud
- Bounded: capped at 200 frames / 60 seconds runtime
- Interruptible: a new page or trigger cancels the in-flight typewriter cleanly

## Author

FiestaBoard
