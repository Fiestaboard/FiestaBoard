# Slot Machine Setup Guide

How to enable Slot Machine and use it on a page.

## Overview

**What it does**: Animates board updates by spinning each column through random characters like a slot-machine reel before locking on the target. Columns lock left-to-right with a configurable stagger.

**Prerequisites**: The **Transition Plugins** beta must be enabled first (Settings → Advanced → Beta Features).

## Quick Setup

1. **Enable** — Open the Integrations page, find Slot Machine under "Transition Plugins", and toggle it on.
2. **Configure** — Optionally adjust `spin_frames`, `column_stagger`, `frame_interval_ms`, and `seed`.
3. **Apply** — Open a page in the editor, set its Transition to "Slot Machine", and save. Or set it as the global default in Settings → Transitions.
4. **View** — The next page transition will spin each column before locking on the new content.

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
