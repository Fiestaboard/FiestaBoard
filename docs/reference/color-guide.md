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

## Using Colors in the Page Editor

In the WYSIWYG editor, color tiles can be inserted using their character codes. The editor shows a preview of how colors will appear on the board.

## Next Steps

- [Character Codes](/docs/reference/character-codes) - Full character reference
- [Page Editor](/docs/features/page-editor) - Creating colored content
- [Weather Plugin](/docs/plugins/weather) - Temperature-based color rules
