# Simple Dissolve Setup Guide

How to enable Simple Dissolve and use it on a page.

## Overview

**What it does**: Animates board updates by flipping changed tiles in a random order, producing a gradual dissolve from the current message to the target.

**Prerequisites**: The **Transition Plugins** beta must be enabled first (Settings → Advanced → Beta Features). Local API and Cloud boards both work — FiestaBoard draws the dissolve itself and sends each frame as a regular board update.

## Quick Setup

1. **Turn on the beta** — Settings → Advanced → Beta Features → **Transition Plugins**. Every installed transition plugin becomes selectable at that point; there is nothing else to switch on.
2. **Tune it (optional)** — `tiles_per_frame`, `frame_interval_ms`, and `seed` live in Simple Dissolve's settings on the Integrations page. Six tiles every 100 ms is the default.
3. **Apply it** — Open a page in the editor, pick **Simple Dissolve** from the **Transition** dropdown in the toolbar, and save. To dissolve everywhere, pick it under Settings → Behavior → Board Transitions instead. A page's own Transition beats the global default, and "Use global default" hands the page back to it.
4. **View** — The next time that page becomes active, the changed tiles flip away in random batches until the new message is complete.

Not sure how chunky the dissolve will look on your board? Open **Transition Lab** from the sidebar, pick Simple Dissolve and two pages, and scrub the frames. The config box there starts from the saved settings and applies your edits to that preview only.

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
- **The board changes instantly, no dissolve** — The **Transition Plugins** beta is off. Turn it on under Settings → Advanced → Beta Features; with it off, pages saved with a plugin transition snap to the target.
- **One page dissolves, another doesn't** — Each page can carry its own Transition. Check that page's Transition dropdown in the editor.
