# Slot Machine Setup Guide

How to enable Slot Machine and use it on a page.

## Overview

**What it does**: Animates board updates by spinning each column through random characters like a slot-machine reel before locking on the target. Columns lock left-to-right with a configurable stagger.

**Prerequisites**: The **Transition Plugins** beta must be enabled first (Settings → Advanced → Beta Features). Any board connection works — the spin is drawn by FiestaBoard and sent as regular board updates, not by the Local API's built-in transitions.

## Quick Setup

1. **Turn on the beta** — Settings → Advanced → Beta Features → **Transition Plugins**. That is the only switch; installed transition plugins have no separate enable step.
2. **Tune the spin (optional)** — `spin_frames`, `column_stagger`, `frame_interval_ms`, and `seed` live in Slot Machine's settings on the Integrations page. The defaults give a six-frame spin with a one-frame cascade between columns.
3. **Apply it** — In the page editor, pick **Slot Machine** from the **Transition** dropdown in the toolbar and save that page. To spin on every page instead, pick it under Settings → Behavior → Board Transitions. Whatever a page sets for itself overrides the global default.
4. **View** — The next page transition will spin each column before locking on the new content.

Slot Machine is the most fun to tune with a preview in front of you. Open **Transition Lab** in the sidebar, pick Slot Machine and two pages, and scrub the frames. The config box there starts from the saved settings and applies your edits to that run only, so you can try `column_stagger: 3` before deciding to keep it.

## Template Variables

None.

## Configuration Reference

| Setting             | Type    | Default | Range       | Description                                                                |
| ------------------- | ------- | ------- | ----------- | -------------------------------------------------------------------------- |
| `spin_frames`       | integer | 6       | 1-30        | Random-character frames each column shows before locking.                   |
| `column_stagger`    | integer | 1       | 0-10        | Frames between adjacent column locks. 0 = simultaneous.                     |
| `frame_interval_ms` | integer | 80      | 0-1000 ms   | Pause between frames. Smaller = faster spin.                                |
| `seed`              | integer | 0       | any         | Fixed integer for deterministic spin. 0 = fresh random each run.            |

No environment variables required.

## Troubleshooting

- **Whole board flashes random characters too long** — Lower `spin_frames` (e.g. to 3-4).
- **All columns lock at the same time, no cascade** — Raise `column_stagger` (try 2-3).
- **Cascade takes too long** — Lower `column_stagger` and/or `frame_interval_ms`.
- **Want a preview that always plays the same way** — Set `seed` to any non-zero integer.
- **The board snaps instead of spinning** — The **Transition Plugins** beta is off. Turn it on under Settings → Advanced → Beta Features; until then, pages saved with a plugin transition jump straight to the target.
- **One page won't spin but the rest do** — That page has its own Transition set to something else. Open it in the page editor and choose Slot Machine, or "Use global default".
