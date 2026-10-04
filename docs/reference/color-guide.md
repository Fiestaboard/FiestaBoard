---
sidebar_position: 3
description: "Use FiestaBoard's 8 color codes to add colored tiles and formatting to your split-flap display layouts."
keywords: [FiestaBoard colors, color codes, display colors, split-flap colors, Vestaboard colors, tile colors]
---

# Color Guide

The split-flap display supports 8 color codes that display solid colored tiles. Use these to add visual emphasis, status indicators, and temperature-based formatting to your pages.

## Available Colors

| Code | Color | Swatch |
|------|-------|--------|
| `{63}` | Red | 🟥 |
| `{64}` | Orange | 🟧 |
| `{65}` | Yellow | 🟨 |
| `{66}` | Green | 🟩 |
| `{67}` | Blue | 🟦 |
| `{68}` | Violet | 🟪 |
| `{69}` | White | ⬜ |
| `{70}` | Black | ⬛ |

## Usage Examples

### Temperature Ranges

Consistent color coding for temperature display:

| Temperature | Color | Code |
|-------------|-------|------|
| ≥ 90°F (32°C) | 🟥 Red | `{63}` - Hot |
| 80–89°F (27–31°C) | 🟧 Orange | `{64}` - Warm |
| 70–79°F (21–26°C) | 🟨 Yellow | `{65}` - Comfortable |
| 60–69°F (16–20°C) | 🟩 Green | `{66}` - Cool |
| 45–59°F (7–15°C) | 🟦 Blue | `{67}` - Cold |
| < 45°F (< 7°C) | 🟪 Violet | `{68}` - Very cold |

### Home Automation Status

| State | Color | Meaning |
|-------|-------|---------|
| Closed / Locked / Off | 🟩 Green | Secure, normal |
| Open / Unlocked / On | 🟥 Red | Attention, alert |

### Star Trek Series

| Series | Color |
|--------|-------|
| The Next Generation (TNG) | 🟨 Yellow `{65}` |
| Deep Space Nine (DS9) | 🟥 Red `{63}` |
| Voyager (VOY) | 🟦 Blue `{67}` |

### Guest WiFi Display

| Element | Color |
|---------|-------|
| Header "GUEST WIFI" | 🟩 Green `{66}` |
| Network name (SSID) | 🟦 Blue `{67}` |
| Password | 🟪 Violet `{68}` |

## Design Principles

When using colors on your board:

1. **Be consistent** - Use the same color for the same meaning across pages
2. **Be purposeful** - Each color should convey information, not just decoration
3. **Use intuitive associations** - Red for alerts, green for good status
4. **Consider accessibility** - Pair colors with text labels for clarity
5. **Less is more** - A few well-placed colors are more effective than a rainbow

## Dynamic Colors

Open a plugin on the **Integrations** page and use **Dynamic Colors** to color a field by its value, for example the hour black from 8pm. Rules for a field are checked in order and the first match wins.

Once a field has a rule, it can be used in two ways:

- `{{date_time.hour}}` shows the value with its color tile in front, such as `⬛ 21`.
- `{{date_time.hour_color}}` shows only the color tile. The variable picker lists it next to the field.

Use one form or the other on a line, not both, or the tile appears twice. Rules saved for a named instance, such as `date_time:pacific`, apply only to that instance.

## Colored Text, Blocks and Icons {#colored-text-blocks-and-icons}

A split-flap board can only show a whole tile in a color. A board that draws pixels, such as an LED matrix, can do more: color the letters themselves, fill a cell's background, and draw small icons. FiestaBoard 10.0.0 adds **extended markup** for those boards.

| Write in a page | Shows |
|-----------------|-------|
| `{{red:HOT}}` | `HOT` in red letters |
| `{{63:HOT}}` | The same, by color code (63 to 70) |
| `{{#ff8800:HOT}}` | `HOT` in any color, as `#rrggbb` |
| `{{black/white:OPEN}}` | `OPEN` in black letters on white cells: text color, then background |
| `{{icon:sun}}` | A sun icon, in one cell |

Forms nest, and a form can hold variables, formulas and color tiles:

```text
{{red:HIGH {{weather.temperature}}°}}
{{icon:sun}} {{green:OPEN {66}}}
```

Colored text and blocks nest up to eight deep. A ninth level shows as plain text, braces and all, in the color of the eighth. Icons and color tiles work at any depth.

The color names are the eight in [Available Colors](#available-colors): `red`, `orange`, `yellow`, `green`, `blue`, `violet` (or `purple`), `white` and `black`. `filled` is a tile only, never a text color.

### Icons

| Icon | Name | Also |
|------|------|------|
| Sun | `sun` | |
| Cloud | `cloud` | |
| Partly cloudy | `partly` | |
| Rain | `rain` | |
| Snow | `snow` | |
| Fog | `fog` | |
| Lightning | `bolt` | `storm` |
| Check | `check` | |
| Cross | `cross` | `x` |
| Up | `up` | |
| Down | `down` | |
| Star | `star` | |
| Bus | `bus` | |
| Train | `train` | |
| Music | `music` | |
| Bell | `bell` | |

`{{icon:heart}}` is not an icon: write the ♥ character instead.

### Which Boards Show What

Every board draws what its **character set** allows, and FiestaBoard fits each message to it:

| Board | Colored text and blocks | Icons |
|-------|-------------------------|-------|
| LED matrix with the 5×7 font | Yes | All of the above |
| LED matrix with the 3×5 font, such as a Divoom Pixoo 64 | Yes | All except `snow`, `partly`, `bus`, `train`, `music` and `bell` |
| Vestaboard, FiestaPanel | The letters, uncolored | The icon's fallback |

An icon a board has no picture for is drawn as its fallback instead: a color tile (`sun` is a yellow tile, `rain` a blue one), a character (`up` is `+`), or a blank. A character the set cannot draw falls back to its uppercase form, then to a blank.

On a Vestaboard or a FiestaPanel, `{{red:HOT}}` shows `HOT` and `{{icon:sun}}` shows a yellow tile, so one page reads well on every board.

### Symbol Shortcuts

The shortcuts `{sun}`, `{star}`, `{cloud}`, `{rain}`, `{snow}`, `{storm}`, `{fog}`, `{partly}`, `{check}` and `{x}` are other names for the icons above: `{sun}` is `{{icon:sun}}`, `{storm}` is `{{icon:bolt}}` and `{x}` is `{{icon:cross}}`. `{heart}` is the ♥ character, one cell.

On a split-flap board they draw the icon's fallback:

| Shortcut | Before 10.0.0 | Now |
|----------|---------------|-----|
| `{sun}`, `{star}` | `*` | Yellow tile |
| `{cloud}`, `{partly}` | `O`, `%` | White tile |
| `{rain}` | `/` | Blue tile |
| `{snow}` | `*` | Violet tile |
| `{storm}` | `!` | Orange tile |
| `{check}` | `+` | Green tile |
| `{x}` | `X` | Red tile |
| `{heart}` | `<3` (two cells) | ♥ (one cell) |
| `{fog}` | `-` | `-` (unchanged) |

To see which of your pages use a shortcut or extended markup, check the startup log, which lists them after an upgrade, or open `/api/system/markup-compat`.

### Variable Values Stay Text

A value a plugin puts into your page is **data**. If a song title or a headline contains `{icon:sun}` or `{red:...}`, it is shown as text with parentheses, never as an icon or a color. Color tiles such as `{63}` in a value still work, so plugins that build art from tiles are unaffected. A plugin can mark a variable as markup on purpose; see [Variable Values Are Data](/docs/development/plugin-guide#variable-format).

## Using Colors in the Page Editor

In the WYSIWYG editor, color tiles can be inserted using their character codes. The editor shows a preview of how colors will appear on the board.

## Next Steps

- [Character Codes](/docs/reference/character-codes) - Full character reference
- [Page Editor](/docs/features/page-editor) - Creating colored content
- [Weather Plugin](/docs/plugins/weather) - Temperature-based color rules
