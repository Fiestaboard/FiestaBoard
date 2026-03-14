# FiestaBoard Logo Lockup Assets

This directory contains the logo lockup images (taco icon + "FiestaBoard" wordmark) used in the docs site navbar and hero.

## Files

| File | Use | Background context |
|------|-----|--------------------|
| `logo-lockup-light.png` | Navbar (light theme) | Light/white backgrounds |
| `logo-lockup-dark.png` | Navbar (dark theme) and hero | Dark navbar, orange gradient hero |

## Layout

- **Vertical alignment:** The taco icon must be vertically aligned with the "FiestaBoard" text (e.g., optical center of the icon on the cap-height or baseline of the text). Avoid the icon appearing to "float" above the text.
- **Export:** Use 2x or 3x resolution for retina displays. The site scales by height (navbar 40px, hero 80px / 56px mobile).

## Color specs

### Light lockup (`logo-lockup-light.png`)

For light backgrounds (white, off-white).

| Element | Color | Notes |
|---------|-------|-------|
| "Fiesta" | `#c07820` | Brand orange (oklch 0.56 0.15 75) |
| "Board" | `#1a1a1a` | Dark gray/black for contrast |
| Taco icon | Board palette | Yellow shell, green filling, red/orange accents; tuned for light background |

### Dark lockup (`logo-lockup-dark.png`)

For dark backgrounds and the orange hero gradient.

| Element | Color | Notes |
|---------|-------|-------|
| "Fiesta" | `#e8a83c` | Brighter orange/amber (oklch 0.78 0.14 75) |
| "Board" | `#ffffff` | White |
| Taco icon | Board palette | Same colors, tuned for contrast on dark |

## Board palette (taco icon)

Reference from `web/src/app/globals.css`:

- Red: `#eb4034`
- Orange: `#f5a623`
- Yellow: `#f8e71c`
- Green: `#7ed321`
- Blue: `#4a90d9`
- Violet: `#9b59b6`

## Replacing assets

1. Create or update the lockup in a design tool (e.g., Figma) per the specs above.
2. Export `logo-lockup-light.png` and `logo-lockup-dark.png` at 2x or 3x.
3. Overwrite the existing files in this directory.
4. Re-check `docs-site/src/css/custom.css`: if the new assets are aligned, you may remove or reduce the `.navbar__logo img { transform: translateY(-4px); }` rule.
