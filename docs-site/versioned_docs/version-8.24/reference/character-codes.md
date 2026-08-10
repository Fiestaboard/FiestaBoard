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

# Convert text to character codes
codes = BoardChars.text_to_codes("HELLO")
# Result: [8, 5, 12, 12, 15]

# Convert codes back to text
text = BoardChars.codes_to_text([8, 5, 12, 12, 15])
# Result: "HELLO"
```

## Board Dimensions

FiestaBoard supports multiple Vestaboard device types:

| Device | Rows | Columns | Total Characters |
|--------|------|---------|------------------|
| **Flagship** | 6 | 22 | 132 |
| **Note** | 3 | 15 | 45 |

Pages are device-specific — each page targets either Flagship or Note, and the editor and preview adapt to the correct dimensions.

## Device-Specific Characters

Some character codes render differently depending on the target device:

| Code | Flagship | Note |
|------|----------|------|
| 62 | `°` (Degree) | `❤` (Heart) |

When creating pages for the Note device, code 62 will display as a red heart icon instead of the degree symbol.

## Next Steps

- [Color Guide](/docs/reference/color-guide) - Detailed color usage and examples
- [Page Editor](/docs/features/page-editor) - Creating content for the board
