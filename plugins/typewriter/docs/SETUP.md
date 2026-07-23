# Typewriter Setup Guide

How to enable the Typewriter transition and use it on a page.

## Overview

**What it does**: Reveals new content on the board left-to-right, one tile (or small batch of tiles) at a time, like a typewriter.

**Prerequisites**: None. Transition plugins ship as part of FiestaBoard and don't require API keys or external accounts.

## Quick Setup

1. **Enable** — Open Settings → Plugins, find Typewriter under "Transition Plugins", and toggle it on.
2. **Configure** — Optionally adjust `chars_per_frame` and `frame_interval_ms` (defaults are a good starting point).
3. **Apply** — Open the page editor for any page, set the Transition picker to "Typewriter", and save. Or set it as the global default in Settings → Transitions.
4. **View** — The next time that page becomes active, the board sweeps left-to-right as the new content lands.

## Template Variables

None.

## Configuration Reference

| Setting             | Type    | Default | Range       | Description                                       |
| ------------------- | ------- | ------- | ----------- | ------------------------------------------------- |
| `chars_per_frame`   | integer | 1       | 1-22        | Tiles flipped per step.                            |
| `frame_interval_ms` | integer | 120     | 0-2000 ms   | Pause between steps in milliseconds.               |

No environment variables required.

## Troubleshooting

- **Transition is too slow** — Lower `frame_interval_ms` or raise `chars_per_frame`.
- **Transition is too fast to see** — Raise `frame_interval_ms` (e.g. to 200-300).
- **Transition not visible** — Confirm the plugin is enabled in Settings → Plugins and selected on the page (or as the global default).
