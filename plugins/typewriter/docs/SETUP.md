# Typewriter Setup Guide

How to enable the Typewriter transition and use it on a page.

## Overview

**What it does**: Reveals new content on the board left-to-right, one tile (or small batch of tiles) at a time, like a typewriter.

**Prerequisites**: The **Transition Plugins** beta must be enabled first (Settings → Advanced → Beta Features). No API keys or external accounts are required, and any board connection works — FiestaBoard sends each frame as a normal board update rather than relying on the Local API's built-in transitions.

## Quick Setup

1. **Turn on the beta** — Settings → Advanced → Beta Features → **Transition Plugins**. Installed transition plugins are usable as soon as the beta is on; there is no separate on/off switch for Typewriter itself.
2. **Tune it (optional)** — The defaults (one tile every 120 ms) are a good starting point. Adjust `chars_per_frame` and `frame_interval_ms` in Typewriter's settings on the Integrations page.
3. **Apply it** — For a single page, open it in the page editor and choose **Typewriter** from the **Transition** dropdown in the toolbar, then save. For every page, choose Typewriter under Settings → Behavior → Board Transitions. A page's own choice wins over the global default; picking "Use global default" clears it.
4. **View** — The next time that page becomes active, the board sweeps left-to-right as the new content lands.

To see the reveal before you commit to it, open **Transition Lab** in the sidebar (it appears once the beta is on). Pick Typewriter and two pages, and step through the frames one at a time. The config box there is seeded with Typewriter's saved settings and lets you try different values for that run only — handy for finding a speed you like before saving it.

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
- **Transition not visible** — Confirm the **Transition Plugins** beta is on (Settings → Advanced → Beta Features). With the beta off, pages saved with a plugin transition snap straight to the target instead.
- **A page ignores the global default** — That page has its own Transition set. Open it in the page editor and pick "Use global default" from the Transition dropdown.
