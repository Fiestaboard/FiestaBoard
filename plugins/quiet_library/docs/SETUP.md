# Quiet Library Setup Guide

Make board updates as quiet as possible by flipping only a few tiles at a time, word by word.

## Overview

Quiet Library is a **transition plugin**: it animates the change from the current message to the next one. It is part of the experimental Transition Plugins beta and is hidden until you opt in.

**Prerequisites**

- FiestaBoard with the **Transition Plugins** beta enabled (Settings → Beta)
- Any board type (Flagship, Note, or a note array)

## Quick Setup

1. **Enable the beta**: Settings → Beta → toggle **Transition Plugins** on.
2. **Enable the plugin**: Integrations → Quiet Library → enable. Optionally adjust *Tiles per step* and *Delay between steps*.
3. **Select the transition**: edit a page and choose **Quiet Library** as its transition, or set it as the system default in Settings → Transitions.
4. **View**: the next time that page is sent, the board updates one small batch of tiles at a time. Preview it any time on the **Transitions** page (Transition Lab).

## Template Variables

None — transition plugins do not provide template variables.

## Configuration Reference

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `batch_size` | integer (1–15) | `6` | Tiles flipped per step; a step never spans two words |
| `step_delay_ms` | integer (1000–60000) | `14500` | Pause between steps (default clears the hardware flap debounce) |

No environment variables.

## Troubleshooting

- **The board snaps instantly instead of animating** — the Transition Plugins beta is off, or the plugin is disabled on the Integrations page. Both must be on.
- **A full-board change takes a long time** — that is the point: with the default settings a completely different message updates in ~14.5s steps. Lower `step_delay_ms` (at the cost of dropped animation steps on hardware, which debounces sends for ~14s) or raise `batch_size` for a faster, louder update.
- **The transition stops partway** — a new page, trigger, or manual send preempted it; the board lands on the newest content. Rotation dwell times shorter than the full transition will regularly do this — that final snap to the new target is expected behavior, not an error.
- **Cloud note arrays** — the Cloud API throttles note-array sends to one per 15 seconds; the runner paces steps automatically, so transitions work but never faster than that floor.
