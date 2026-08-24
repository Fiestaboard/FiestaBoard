---
sidebar_position: 2
description: "Reference table of split-flap character codes used by FiestaBoard and Vestaboard for display encoding."
keywords: [FiestaBoard character codes, split-flap characters, Vestaboard encoding, character map, display characters]
---

# Character Codes

The split-flap display uses character codes to represent letters, numbers, and symbols. This reference lists all available codes.

## Letters (Codes 1–26)

| Code | Character | | Code | Character |
|------|-----------|-|------|-----------|
| 1 | A | | 14 | N |
| 2 | B | | 15 | O |
| 3 | C | | 16 | P |
| 4 | D | | 17 | Q |
| 5 | E | | 18 | R |
| 6 | F | | 19 | S |
| 7 | G | | 20 | T |
| 8 | H | | 21 | U |
| 9 | I | | 22 | V |
| 10 | J | | 23 | W |
| 11 | K | | 24 | X |
| 12 | L | | 25 | Y |
| 13 | M | | 26 | Z |

## Numbers (Codes 27–36)

| Code | Character |
|------|-----------|
| 27 | 1 |
| 28 | 2 |
| 29 | 3 |
| 30 | 4 |
| 31 | 5 |
| 32 | 6 |
| 33 | 7 |
| 34 | 8 |
| 35 | 9 |
| 36 | 0 |

## Special Characters

| Code | Character | Description |
|------|-----------|-------------|
| 0 | ` ` | Blank/Space |
| 37 | `!` | Exclamation |
| 38 | `@` | At sign |
| 39 | `#` | Hash |
| 40 | `$` | Dollar |
| 41 | `(` | Open paren |
| 42 | `)` | Close paren |
| 44 | `-` | Hyphen |
| 46 | `+` | Plus |
| 47 | `&` | Ampersand |
| 48 | `=` | Equals |
| 49 | `;` | Semicolon |
| 50 | `:` | Colon |
| 52 | `'` | Apostrophe |
| 53 | `"` | Quote |
| 54 | `%` | Percent |
| 55 | `,` | Comma |
| 56 | `.` | Period |
| 59 | `/` | Slash |
| 60 | `?` | Question |
| 62 | `°` | Degree |

## Color Codes (63–70)

These codes display solid colored tiles:

| Code | Color | Common Use |
|------|-------|------------|
| 63 | 🟥 Red | Alerts, hot temperatures |
| 64 | 🟧 Orange | Warm temperatures |
| 65 | 🟨 Yellow | Comfortable, warnings |
| 66 | 🟩 Green | Good status, success |
| 67 | 🟦 Blue | Cold temperatures |
| 68 | 🟪 Violet | Very cold, accents |
| 69 | ⬜ White | Backgrounds |
| 70 | ⬛ Black | Backgrounds |

See the [Color Guide](/docs/reference/color-guide) for detailed usage.

## Using Character Codes in Code

```python
from src.board_chars import BoardChars

# Convert a whole string to character codes
codes = BoardChars.text_to_codes("HELLO")
# Result: [8, 5, 12, 12, 15]

# Look up a single character's code
code = BoardChars.get_char_code("H")
# Result: 8

# Look up a color code by name
red = BoardChars.get_color_code("red")
# Result: 63
```

> **Note:** `BoardChars` only maps text to codes, not the reverse. To turn a code
> back into a character, read it off the tables above.

## Board Dimensions

FiestaBoard supports multiple Vestaboard device types:

| Device | Rows | Columns | Total Characters |
|--------|------|---------|------------------|
| **Flagship** | 6 | 22 | 132 |
| **Note** | 3 | 15 | 45 |

Pages are device-specific — each page targets either Flagship or Note, and the editor and preview adapt to the correct dimensions.

## Code 62: Degree or Heart

Character code 62 is one code with two possible flaps, and which one you get depends on the physical board:

| Board | Code 62 draws |
|-------|---------------|
| Note (and Note arrays) | `❤` (Heart) |
| Flagship shipped before 2026 | `°` (Degree) |
| Flagship shipped from 2026 | `❤` (Heart) |

Vestaboard replaced the degree flap with a heart on newly-manufactured Flagships: *"Every new Vestaboard purchased will ship with the heart in place of the degree symbol."* Nothing FiestaBoard can query tells the two apart — there is no serial number or API field that reports it — so **you tell FiestaBoard which flap your board has**.

Set it per board in **Settings → Hardware** (or in the setup wizard when adding a board), under **Code 62 flap**. Boards default to **Degree**, so if you have an older Flagship there is nothing to change.

The setting only affects what FiestaBoard *draws* in its previews, so the preview matches your wall. It never changes what is sent to the board: both glyphs are character code 62 on the wire, and the board draws whichever flap it physically has. It is a per-board setting, so a household with one older and one newer Flagship previews each correctly.

The setting is not offered for Note devices — Note hardware has only ever carried the heart flap.

In a template, type the degree symbol (`°`) or a heart (`❤`) and you get code 62 either way.

## Next Steps

- [Color Guide](/docs/reference/color-guide) - Detailed color usage and examples
- [Page Editor](/docs/features/page-editor) - Creating content for the board
