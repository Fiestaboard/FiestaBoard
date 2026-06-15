# Random Plugin Setup Guide

Display randomly selected values on your Vestaboard, refreshed on a schedule you control.

## Overview

The Random plugin needs no API key or external service — it generates all values locally.

**What it does:** Picks a random item from your custom list, flips a coin, and selects a random board color. Each value is re-rolled at your configured refresh interval.

**Prerequisites:** None. No API key required.

## Quick Setup

### 1. Enable the plugin

In the FiestaBoard web UI:

1. Open **Integrations**.
2. Find **Random** and toggle it on.

### 2. Configure

1. Click **Configure** on the Random card.
2. Set your **Choices** — a list of 2–10 strings the plugin picks from (e.g. `Pizza`, `Tacos`, `Sushi`).
3. Optionally adjust the **Refresh Interval** (default: 60 seconds).
4. Click **Save Changes**.

### 3. Create a board template

In **Pages**, create or edit a page template and add random variables. A minimal example:

```jinja
{center}TODAY'S PICK
{{random.choice}}

COIN FLIP: {{random.coin_flip}}
```

### 4. View on your board

Save the page. On the next refresh, your board will show a fresh random pick.

![Random displayed on a Vestaboard](./board-display.png)

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
The value is cached until `refresh_seconds` expires. To force an immediate re-roll, you must save a config that is *different* from the current one — the cache only clears when the saved values actually change.

> **Tip:** A quick way to force a refresh: temporarily add a dummy choice (e.g. `"temp"`), save, then remove it and save again. Each save with a changed value clears the cache and picks a new result immediately.

**Validation error: "choices must have at least 2 items"**
The `choices` list requires at least 2 entries. Add a second option to continue.

**Validation error: "choices must have at most 10 items"**
Trim your list to 10 items or fewer.
