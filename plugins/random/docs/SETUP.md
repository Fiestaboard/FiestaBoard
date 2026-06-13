# Random Plugin Setup Guide

Display randomly selected values on your FiestaBoard, refreshed on a schedule you control.

## Overview

The Random plugin needs no API key or external service — it generates all values locally.

**What it does:** Picks a random item from your custom list, flips a coin, and selects a random board color. Each value is re-rolled at your configured refresh interval.

**Prerequisites:** None. No API key required.

## Quick Setup

1. **Enable** — Open Integrations, find Random, and toggle it on.
2. **Configure** — Set your list of choices (e.g. dinner options, team names). Optionally adjust the refresh interval.
3. **Template** — Add `{{random.choice}}`, `{{random.coin_flip}}`, or `{{random.color}}` to any page template.
4. **View** — Save and your board will show a fresh random pick on each refresh.

## Template Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{{random.choice}}` | Random pick from your configured choices | `Pizza` |
| `{{random.coin_flip}}` | Heads or Tails | `Tails` |
| `{{random.color}}` | Random board color as a rendered color tile (a solid colored square) | _(colored square)_ |
| `{{random.color_name}}` | Random board color as text — `red`, `orange`, `yellow`, `green`, `blue`, or `violet` | `green` |

## Configuration Reference

### Settings

| Setting | Type | Required | Default | Description |
|---------|------|----------|---------|-------------|
| `enabled` | boolean | No | `true` | Enable or disable the plugin |
| `choices` | array of strings | No | `["Heads", "Tails"]` | List of 2–10 strings to pick from for `{{random.choice}}` |
| `refresh_seconds` | integer | No | `60` | Seconds between re-rolls (minimum: 60, maximum: 86400) |

### Environment Variables

None required.

## Troubleshooting

**`random.choice` always shows the same value**
The value is cached until `refresh_seconds` expires. To force a refresh, save the plugin config — this clears the cache and picks a new value immediately.

**Validation error: "choices must have at least 2 items"**
The `choices` list requires at least 2 entries. Add a second option to continue.

**Validation error: "choices must have at most 10 items"**
Trim your list to 10 items or fewer.
