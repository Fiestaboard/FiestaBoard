# Random Plugin

Display randomly selected values on your board, refreshed at a configurable interval.

![Random Display](./docs/board-display.png)

**→ [Setup Guide](./docs/SETUP.md)**

## Overview

The Random plugin generates fresh random values on a schedule you control. It exposes three template variables: a pick from your own custom list of choices, a classic coin flip (Heads or Tails), and a random board color. Values are re-rolled at the configured refresh interval (default: every 60 seconds).

## Template Variables

### Selection

| Variable | Description | Example |
|----------|-------------|---------|
| `{{random.choice}}` | Randomly selected item from your configured choices list | `Option A` |

### Presets

| Variable | Description | Example |
|----------|-------------|---------|
| `{{random.coin_flip}}` | Coin flip result | `Heads` |
| `{{random.color}}` | Random board color name | `green` |

## Example Templates

**Coin flip:**
```
COIN FLIP
{{random.coin_flip}}
```

**Pick from a custom list:**
```
TONIGHT'S DINNER
{{random.choice}}
```

**Random color tile line:**
```
{{random.color}}
```

**Combined:**
```

FLIP: {{random.coin_flip}}
PICK: {{random.choice}}

COLOR: {{random.color}}

```

## Configuration

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `enabled` | boolean | `true` | Enable or disable the plugin |
| `choices` | array of strings | `["Heads", "Tails"]` | 2–10 options for the `random.choice` variable |
| `refresh_seconds` | integer | `60` | How often to pick new random values (60–86400 seconds) |

## Features

- Pick a random item from any list of 2–10 strings you define
- Built-in coin flip (Heads / Tails) always available as `random.coin_flip`
- Built-in random board color (excludes `filled`) always available as `random.color`
- Configurable refresh interval — values change every N seconds

## Author

FiestaBoard Team
