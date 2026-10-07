---
sidebar_position: 9
description: "Draw full-color pixel art, shapes, and plugin-generated pictures inside a page on an LED pixel display like the Divoom Pixoo, with text hidden under or flowing around each canvas."
keywords: [FiestaBoard pixel canvas, pixel art, LED matrix display, Divoom Pixoo, page canvas, generative art, pixel drawing, LED pixel board]
---

# Pixel Canvases

A pixel canvas is a drawing that lives inside a page: a block of character cells where an LED pixel display shows any picture you like, in any RGB color, next to the page's text.

## Overview

A page's template fills the board with characters. A canvas claims a rectangle of those character cells and draws pixels there instead. You can paint it by hand, describe it with shapes, or let a plugin draw it for you.

- **A page can hold up to 8 canvases.** Each one is placed by character cells, so it lines up with the text around it.
- **Canvases draw on LED pixel-matrix displays only**, such as a Divoom Pixoo. A split-flap board (a Vestaboard) or another fixed-character display shows the page's text and leaves each canvas area blank.
- **Text can hide under a canvas or flow around it.** With `hide` (the default), the text under the canvas is blanked. With `flow`, the canvas's columns are taken out of each row it covers and the text wraps into the space that is left.
- **A canvas can bleed to the edge of the panel.** A pixel display has a thin margin around its character grid; bleed lets a canvas that touches the grid edge cover that margin too.

## Adding a Canvas in the Page Builder

The canvas tools appear in the page builder when the page is being edited for an LED pixel board. For any other board they are hidden; a page that already has canvases shows a short notice that this board leaves canvas areas blank.

1. Open a page in the page builder and find the **Canvases** section.
2. Select **Add canvas**. The new canvas gets an id (lowercase letters, digits, `_` or `-`, up to 16 characters) that you can change.
3. Set its **area**: the first row and column (counted from 1) and how many rows and columns it covers. You can type the numbers or drag across the preview grid to select the cells.
4. Choose the canvas options:
   - **Bleed**: which sides extend to the panel edge (top, left, right, bottom, or all). A side only bleeds where the area touches that edge of the grid.
   - **Scale**: how many panel pixels each canvas pixel takes, from 1 to 8. A scale of 2 draws chunky, double-size pixels.
   - **Text**: **Hide** blanks the text under the canvas; **Flow** wraps the text around it.
5. Draw the canvas with one of the three tabs below. The live preview shows the result on the board, and any problem the server finds (a bad color, a variable with no value) is listed under it.

To remove a canvas, select **Delete** on it. The raw template view shows a read-only `{canvas:<id>}` marker on the canvas's first row so you can see where it sits; the marker is not part of the template text.

### Draw

The **Draw** tab is a pixel pad at the canvas's real pixel size, with zoom.

- **Brush** paints one pixel; drag to paint a stroke.
- **Eraser** makes pixels transparent, so the board shows what is under them.
- **Fill** paints every connected pixel of the same color.
- **Eyedropper** picks a color from the drawing.
- **Color** opens a full RGB color picker.

The pad keeps the canvas's palette for you: each color you use gets a one-character key, up to 62 colors. From the keyboard, the arrow keys move a cursor across the pad and Space paints the pixel under it with the current tool.

### Shapes

The **Shapes** tab is a list of shapes drawn in order: rectangles, circles, ellipses, lines, polygons, text, and gradients. Add, edit, reorder, or delete them. Every field accepts a number or color, or a `{{…}}` expression; use the variable picker to insert a plugin variable. For anything the list editor does not cover, switch to the JSON editor; the server's validation errors show next to it.

### Source

The **Source** tab lets a plugin draw the canvas. Pick one of your plugins' canvas variables (a variable whose manifest marks it `"format": "canvas"`), such as `{{generative_ai_art.canvas}}`, or type any expression that yields a drawing. When the source has no value, the canvas falls back to its own drawing, or stays empty if it has none.

## Canvas Format

Pages store each canvas as JSON beside the template. You can write this JSON yourself in the Shapes tab's JSON editor, in the API, or by asking the AI assistant.

```json
{
  "id": "sky",
  "area": {"row": 1, "col": 1, "rows": 4, "cols": 16},
  "bleed": ["top", "left", "right"],
  "scale": 1,
  "text": "hide",
  "content": {
    "size": [64, 32],
    "background": "#000000",
    "palette": {"k": "#000000", "y": "#ffcc00"},
    "shapes": [],
    "pixels": ["kkyy..", "kyyy.."]
  },
  "source": "{{generative_ai_art.canvas}}"
}
```

| Field | Required | Meaning |
|---|---|---|
| `id` | Yes | 1–16 characters of `a-z`, `0-9`, `_`, `-`; unique in the page |
| `area` | Yes | `row`, `col` (1-based), `rows`, `cols`: the character cells it covers |
| `bleed` | No | Sides that extend to the panel edge: `top`, `left`, `right`, `bottom`, or `all` |
| `scale` | No | Panel pixels per canvas pixel, 1–8 (default 1) |
| `text` | No | `hide` (default) or `flow` |
| `content` | One of the two | The drawing itself (see below) |
| `source` | One of the two | A `{{…}}` expression that yields a content object; when it has no value, `content` is drawn instead |

### Area and size

An area must start inside the page grid, but it may run past the right or bottom edge: it is clamped to the board it draws on. So `{"row": 1, "col": 1, "rows": 96, "cols": 128}` means "the whole board" on every board size. When a board's grid changes (for example, switching an LED board's text size), FiestaBoard scales each canvas area to the new grid.

### Content

| Field | Meaning |
|---|---|
| `size` | `[width, height]` the drawing is made at, each 1–128. Default: the canvas's own pixel size. A drawing at another size is scaled to fit (nearest-neighbor, aspect kept, centered), so a plugin can draw at 64×64 without knowing the area |
| `background` | A color that fills the canvas first. Default: transparent |
| `palette` | Up to 62 one-character keys (`A-Z`, `a-z`, `0-9`) mapped to colors, used by `pixels` and usable anywhere a color goes |
| `shapes` | Up to 256 shapes, drawn in order after the background |
| `pixels` | Up to 128 rows of up to 128 characters, drawn last: each character is a palette key, or `.` for transparent |

**Colors** can be `#rgb`, `#rrggbb`, a palette key, a board color name (`red`, `orange`, `yellow`, `green`, `blue`, `violet`, `white`, `black`), or `none` / `transparent`.

### Shapes

Coordinates are in the content's own space; numbers may have decimals.

| `type` | Fields |
|---|---|
| `rect` | `x`, `y`, `w`, `h`, optional `fill`, `stroke` |
| `circle` | `cx`, `cy`, `r`, optional `fill`, `stroke` |
| `ellipse` | `cx`, `cy`, `rx`, `ry`, optional `fill`, `stroke` |
| `line` | `x1`, `y1`, `x2`, `y2`, `stroke`, optional `width` (1–16, default 1) |
| `polygon` | `points` (3–256 `[x, y]` pairs), optional `fill`, `stroke` |
| `text` | `x`, `y` (top-left), `text`, `color`, optional `font` (`"3x5"` or `"5x7"`, default `"5x7"`) |
| `gradient` | `from`, `to`, optional `x`, `y`, `w`, `h` (default: the whole canvas), `angle` in degrees (0 = left to right, 90 = top to bottom, the default) |

### Expressions, conditions, and loops

Any shape field can be a `{{…}}` expression, using the same language as page templates (see [Template Expressions](../reference/template-formulas.md)). A field that is one expression takes its value as is (a number stays a number).

Every shape also accepts:

- `"if": "{{…}}"`: the shape is skipped when the expression is false or empty.
- `"foreach": "{{…}}"` and `"as": "p"`: the shape repeats for each item of a list. Inside it, `p.index` is the item's position (from 0), `p.value` is the item, and a field of an object item is `p.<field>`. Without `as`, the name is `item`.

A field that cannot be worked out (a variable with no value, text where a number belongs) skips that shape, or that one loop item, and is reported as an issue; the rest of the canvas still draws.

## Examples

A sun in the top-right corner that only shows when it is warm, with the text flowing around it:

```json
{
  "id": "sun",
  "area": {"row": 1, "col": 12, "rows": 3, "cols": 5},
  "bleed": ["top", "right"],
  "text": "flow",
  "content": {
    "size": [24, 24],
    "shapes": [
      {"type": "circle", "cx": 12, "cy": 12, "r": 7, "fill": "#ffcc00", "if": "{{weather.temperature > 60}}"},
      {"type": "circle", "cx": 12, "cy": 12, "r": 7, "stroke": "#88aaff", "if": "{{weather.temperature <= 60}}"}
    ]
  }
}
```

A small bar chart, one bar per item in a plugin's list, over a sky gradient:

```json
{
  "id": "chart",
  "area": {"row": 4, "col": 1, "rows": 4, "cols": 16},
  "content": {
    "size": [64, 32],
    "shapes": [
      {"type": "gradient", "from": "#001133", "to": "#334477"},
      {"type": "rect", "foreach": "{{my_plugin.readings}}", "as": "p",
       "x": "{{p.index * 8}}", "y": "{{32 - p.level}}", "w": 6, "h": "{{p.level}}", "fill": "green"}
    ]
  }
}
```

A hand-drawn heart in pixel rows:

```json
{
  "id": "heart",
  "area": {"row": 2, "col": 7, "rows": 1, "cols": 2},
  "content": {
    "palette": {"r": "#ff2244"},
    "pixels": [".r.r.", "rrrrr", "rrrrr", ".rrr.", "..r.."]
  }
}
```

## Limits

| Limit | Value |
|---|---|
| Canvases per page | 8 |
| Palette keys | 62 |
| Shapes per canvas | 256 (1024 after `foreach` repeats) |
| `pixels` | 128 rows × 128 characters |
| Content `size` | 1–128 each way |
| `scale` | 1–8 |
| Polygon points | 3–256 |
| Text shape length | 256 characters |

## AI Assistant and API

The AI assistant and the MCP tools can create canvases too: `create_page` and `update_page` accept a `canvases` list in the format above, `render_page_preview` previews a page with canvases on a pixel board and reports any canvas issues, and `validate_template` checks canvases before you save. Ask, for example, "add a full-board canvas drawn by the generative art plugin to my morning page".

In the REST API, `canvases` is a field of a page (see the [API reference](../reference/api-endpoints.md)). Responses for a pixel board carry the drawn canvases as `layers`, and any drawing problems as `canvas_issues`.

## For Plugin Developers

A plugin can draw canvases by exposing a variable with `"format": "canvas"` whose value is a content object. See [Drawing pixel canvases](../development/plugin-guide.md#pixel-canvases) in the Plugin Development Guide.
