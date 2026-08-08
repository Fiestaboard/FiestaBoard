---
sidebar_position: 25
description: "Display randomly selected values on your split-flap display with FiestaBoard. Coin flips, custom lists, and random colors — no API key required."
keywords: [FiestaBoard random, coin flip display, random pick, split-flap random, Vestaboard random]
---

# Random

Display randomly selected values on the board, refreshed on a schedule you control. **No API key required.**

## Overview

The Random plugin generates fresh values on a configurable interval:

- Pick a random item from your own list of 2–10 choices
- Built-in coin flip (Heads or Tails)
- Random board color as a rendered tile or as a color name
- Values re-roll at your configured refresh interval (default: every 60 seconds)

## Setup

1. Open **http://localhost:4420**
2. Go to the **Integrations** page
3. Toggle **Random** on
4. Click **Configure** to set your choices list and refresh interval
5. Click **Save Changes**

:::tip
Random requires no external service or API key. All values are generated locally.
:::

## Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{{random.choice}}` | Random pick from your configured choices list | `Pizza` |
| `{{random.coin_flip}}` | Coin flip result | `Heads` |
| `{{random.color}}` | Random board color as a rendered color tile | _(colored square)_ |
| `{{random.color_name}}` | Random board color name as text | `green` |

> Colors are limited to red, orange, yellow, green, blue, and violet. White and black are excluded because they render inverted on white-model boards.

## Example Templates

**Coin flip:**

```jinja
COIN FLIP
{{random.coin_flip}}
```

**Pick from a custom list:**

```jinja
TONIGHT'S DINNER
{{random.choice}}
```

**Random color tile with name:**

```jinja
{{random.color}} {{random.color_name}}
```

**Combined:**

```jinja

FLIP: {{random.coin_flip}}
PICK: {{random.choice}}

COLOR: {{random.color}}

```

## Next Steps

- [Date & Time Plugin](/docs/plugins/date-time) -- Display the current date and time
- [Plugins Overview](/docs/plugins/overview) -- See all available plugins
