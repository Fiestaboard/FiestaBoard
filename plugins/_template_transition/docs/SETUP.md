# My Transition Setup Guide

How to enable and use this transition plugin.

## Overview

**What it does**: (one-line description)

**Prerequisites**: The **Transition Plugins** beta must be enabled first (Displays → choose a split-flap display → Transition → **Transition Plugins**; one switch for the whole install). List any API keys / accounts your plugin needs here.

## Quick Setup

1. **Enable** — Turn on the **Transition Plugins** beta in a display's **Transition** section. Installed transition plugins have no enable step of their own.
2. **Configure** — Adjust the settings to your taste.
3. **Apply** — Set it as a page's transition, or as a display's transition in Displays → (a display) → Transition.
4. **View** — Watch the next page transition use your effect.

## Template Variables

None.

## Configuration Reference

| Setting    | Type    | Default | Range     | Description                          |
| ---------- | ------- | ------- | --------- | ------------------------------------ |
| `speed_ms` | integer | 100     | 0-2000 ms | Time between frames in milliseconds. |

No environment variables required.

## Troubleshooting

- **Transition too fast / slow** — Adjust `speed_ms`.
