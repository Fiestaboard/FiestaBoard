# Simple Dissolve Setup Guide

How to enable Simple Dissolve and use it on a page.

## Overview

**What it does**: Animates board updates by flipping changed tiles in a random order, producing a gradual dissolve from the current message to the target.

**Prerequisites**: None.

## Quick Setup

1. **Enable** — Open Settings → Plugins, find Simple Dissolve under "Transition Plugins", and toggle it on.
2. **Configure** — Optionally adjust `tiles_per_frame`, `frame_interval_ms`, and `seed`.
3. **Apply** — Open a page in the editor, set its Transition to "Simple Dissolve", and save. Or set it as the global default in Settings → Transitions.
4. **View** — The next page transition will dissolve into the new content.

## Template Variables

None.

## Configuration Reference

| Setting             | Type    | Default | Range       | Description                                                                |
| ------------------- | ------- | ------- | ----------- | -------------------------------------------------------------------------- |
| `tiles_per_frame`   | integer | 6       | 1-132       | Tiles flipped per step.                                                     |
| `frame_interval_ms` | integer | 100     | 0-2000 ms   | Pause between steps in milliseconds.                                        |
| `seed`              | integer | 0       | any         | Fixed integer for deterministic ordering. 0 = fresh random each run.        |

No environment variables required.

## Troubleshooting

- **Dissolve looks the same every time** — You've set a non-zero `seed`. Set it back to 0 for fresh randomness.
- **Want a preview that always plays the same way** — Set `seed` to any non-zero integer.
- **Transition feels chunky** — Lower `tiles_per_frame` and/or raise `frame_interval_ms`.
- **Transition is too slow** — Raise `tiles_per_frame` or lower `frame_interval_ms`.
