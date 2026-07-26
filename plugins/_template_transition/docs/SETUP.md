# My Transition Setup Guide

How to enable and use this transition plugin.

## Overview

**What it does**: (one-line description)

**Prerequisites**: The **Transition Plugins** beta must be enabled first (Settings → Advanced → Beta Features). List any API keys / accounts your plugin needs here.

## Quick Setup

1. **Enable** — Open the Integrations page, find this plugin under "Transition Plugins", and toggle it on.
2. **Configure** — Adjust the settings to your taste.
3. **Apply** — Set it as a page's transition (or as the global default in Settings → Transitions).
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
