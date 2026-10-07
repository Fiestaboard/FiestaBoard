# Pixel canvas — design record

<!-- cspell:words luma Colours colours rasterise rasterised rasterisation rasteriser neighbour letterboxed -->

Owner-approved direction (chat, 2026-10-06/07): canvases live INSIDE normal pages, a page can hold several, a canvas
can bleed to the panel border, content is stored data beside the template (option 1), any pixel any RGB colour,
drawable by hand and by plugins (target: generative-ai-art), plugin values can drive canvases (expressions,
conditionals, loops), text can hide under or flow around a canvas. Pixel-matrix displays only; fixed-character-set
boards show the text and leave canvas areas blank. Owner: "keep working, don't stop until PRs are into next and the
generative art plugin is updated" (merges themselves are owner-only: permission classifier).

## 1. Data model

`Page.canvases: list[Canvas] | None` (≤ 8 per page). A canvas:

```json
{
  "id": "sky",                                   // [a-z0-9_-]{1,16}, unique in the page
  "area": {"row": 1, "col": 1, "rows": 4, "cols": 16},   // 1-based character cells of the page grid
  "bleed": ["top", "left", "right"],             // or ["all"]; sides only honoured where the area touches the grid edge
  "scale": 1,                                    // panel pixels per canvas pixel (1..8)
  "text": "hide",                                // "hide" (default) | "flow"
  "content": {                                   // optional when "source" is set
    "size": [64, 32],                            // optional: content coordinate space; default = canvas pixel size
    "background": "#000000",                     // optional; default transparent
    "palette": {"k": "#000000", "y": "#ffcc00"}, // ≤ 62 single-char keys [A-Za-z0-9]; "." means transparent
    "shapes": [ ... ],                           // ≤ 256, drawn in order after background
    "pixels": ["kkyy..", "..."]                  // ≤ 128 rows × ≤ 128 chars, drawn last; "." transparent
  },
  "source": "{{generative_ai_art.canvas}}"      // optional: a template expression yielding a content object
}
```

Colours: `#rgb`, `#rrggbb`, a palette key, a board colour name (`red orange yellow green blue violet white black`),
or `none`/`transparent`.

Shapes (coordinates in the content space; numbers may be floats; every field may be a `{{…}}` expression):

- `rect {x,y,w,h, fill?, stroke?}` · `circle {cx,cy,r, fill?, stroke?}` · `ellipse {cx,cy,rx,ry, fill?, stroke?}`
- `line {x1,y1,x2,y2, stroke, width?=1}` · `polygon {points:[[x,y],…], fill?, stroke?}`
- `text {x,y, text, color, font?: "3x5"|"5x7"}` (LED fonts; top-left anchored)
- `gradient {x?,y?,w?,h?, from, to, angle?=90}` (linear, default whole canvas, angle in degrees, 90 = top→bottom)
- any shape: `"if": "{{expr}}"` (falsy → skipped); `"foreach": "{{array_expr}}", "as": "p"` (repeats the shape with
  `p` = item, `p.index` = 0-based index; item fields addressable as `p.<field>`, scalars as `p.value`).

Content `size` decouples drawing resolution from the region: content is rasterised at `size` then scaled
nearest-neighbour to the canvas pixel size (aspect preserved, centred, letterboxed transparent). So a plugin can draw
at 64×64 without knowing the region.

`source`: evaluated at render; must yield a content object (dict). A plugin exposes it as a variable with manifest
`"format": "canvas"`. Invalid/missing source → stored `content` if any, else the canvas is empty (transparent).

Validation is shared (core Pydantic; TS mirror for the editor). Limits keep pages.json small (64×64 palette rows ≈ 4 KB).

Storage: `pages.json` schema v6 migration sets `canvases: null` on every page that lacks the key (idempotent; logs
the count), per CLAUDE.md "Page Schema Versioning". `_SHARE_FIELDS` + `update()` nullable allow-list gain `canvases`. TS `Page` type mirrors.

Text-size switch (board grid retarget, core #2225): canvas areas scale proportionally (rows/cols rounded, ≥1,
clamped to the grid).

## 2. Geometry

Board grid = `grid_layout(W, H, font)` → origin `(ox, oy)`, pitch `(gw+sx, gh+sy)`.
Area → pixel rect: `x0 = ox + (col-1)*px`, `y0 = oy + (row-1)*py`, `x1 = ox + (col-1+cols)*px - sx`,
`y1 = oy + (row-1+rows)*py - sy` (exclusive; gutters inside the area belong to the canvas). Bleed: a side touching the
grid edge extends to the panel edge (`left`→0, `top`→0, `right`→W, `bottom`→H). Canvas pixel size =
`floor(w/scale) × floor(h/scale)`, centred in the rect. Non-pixel boards: no rect; the area's cells are blank.

## 3. Render pipeline (core)

1. Page render (`PageService.render_page`): template lines render as today, but with per-row free spans:
   - `flow` canvases remove their columns from each row they cover; text (wrap on) flows into free spans in reading
     order (left span, then right span, next row); words never split; alignment applies within the span; no-wrap
     lines clip at the span end.
   - `hide` canvases: text renders as today; cells under the area are blanked afterwards.
2. Canvases evaluate (`source` → content; field expressions, `if`, `foreach`) through the template engine's
   expression evaluator with the page's variable context, then rasterise (pure Python) to `CanvasLayer(x, y, w, h,
   rgba: bytes)` in panel pixels. Only for pixel-matrix boards (`is_led_pixel_model`); others get no layers.
3. `DisplayResult` carries `layers`; the content key (dedupe, in-flight, preview cache) includes a hash of the layers.
4. Projection unchanged (cells); covered cells are blank.
5. LED renderer: `LedLayout.layers`, op kind `"bitmap"` painted after cell ops (alpha > 0 overwrites; monochrome
   boards light pixels whose luminance ≥ 50% in the panel colour). `layout_message/layout_cells(..., layers=())`.
6. Transitions: per-pixel kinds (slide/wipe/fade/dissolve) work on rasterised frames (layers included). Per-cell kinds
   (flip/cascade) keep the before layers for the first half of the frames and the after layers for the second half.
7. Output plugins: frames reach `write_cells` / `write_transition` as `RichCellFrame`s that are a list subclass with a
   `.layers` attribute (backward compatible: old plugins see a plain list and ignore layers). `FrameCache` equality
   includes layers. LED output plugins pass `getattr(frame, "layers", ())` to `layout_message`.
8. APIs: batch preview, board current message, send-page responses add `layers: [{x,y,w,h,rgba(base64)}]` for pixel
   boards. `DisplayProfile` gains feature `"pixels"` (pixel-matrix boards) and `ai_brief()` mentions canvases.

## 4. FiestaUI

`LedMatrixDisplay` / `DisplayPreview` accept `layers?: LedBitmapLayer[]` (`{x,y,width,height,rgba}` with `rgba` as
`Uint8ClampedArray` or base64). LED layout gains op kind `bitmap`; `rasterizeLedOps` paints it; the canvas painter
draws bitmap pixels with the same dot look. Core does all canvas rasterisation; FiestaUI only draws bitmaps.

## 5. Web editor

Page builder, LED boards only: "Add canvas" creates a canvas over a dragged cell region; canvases show as labelled
outlines over the template grid; the canvas panel has tabs **Draw** (pixel pad: brush, eraser, fill, picker, any
colour; writes `content.pixels`/`palette`), **Shapes** (list editor with JSON fallback; fields accept `{{…}}` with
the variable picker), **Source** (plugin variables with `format: canvas`), plus area/bleed/scale/text-mode controls.
Raw template view shows `{canvas:<id>}` on the canvas's first row as a read-only marker. Preview via the server batch
preview (layers). Non-LED boards: canvas UI hidden; a page with canvases shows a notice.

## 6. MCP / AI

`create_page`/`update_page`/`render_page_preview` accept `canvases`; `validate_template` validates them. AI teaching
addendum gets a compact canvas section within the 41 KB budget.

## 7. Plugins

- Divoom Pixoo: pass `frame.layers` into `layout_message` (still renders cells-only frames identically).
- generative-ai-art: new variable `canvas` (`format: canvas`): on RGB pixel displays (`self.board.display`
  supports `"pixels"`), ask the model for a full-colour scene (hex colours, shapes incl. gradient) and return a
  content object at `size` = the board's pixel size (or 64×64); existing `art` (tile text) unchanged for split-flap.
  Demo page template gains a full-board canvas sourced from it.

## 8. Not in v1

Animated canvases, image upload/import, per-pixel transitions inside per-cell kinds, canvases on FiestaPanel
split-flap TVs, free (non-cell) placement.

## 9. PR plan (stacked on core #2225 `feat/led-text-size`)

1. core `feat/canvas-engine`: `src/canvas/` models + validation, geometry, expression evaluation, rasteriser,
   `CanvasLayer`; tests incl. goldens.
2. FiestaUI `feat/led-bitmap-layers`: bitmap op + `layers` prop + stories/tests (parallel with 1).
3. core `feat/canvas-pages`: Page.canvases + migration + share + render pipeline (flow/hide, layers, content key),
   LED layers + transitions + output frames + FrameCache + APIs + DisplayProfile (after 1).
4. core `feat/canvas-editor`: web editor + TS types + MCP + AI teaching + docs (after 3; FiestaUI bump after 2 releases).
5. divoom-pixoo: layers passthrough (after 3).
6. generative-ai-art: `canvas` variable (after 1 for the format; tests against 3).

## 10. What core PR 3 (`feat/canvas-pages`) implements

- **Storage.** `Page.canvases` on `Page` / `PageCreate` / `PageUpdate` (`PageUpdate.canvases: null` clears them) and
  on the import preview. `pages.json` schema v6 (`_migrate_v5_to_v6`) adds `canvases: null` where absent. Canvases
  are stored in their JSON form (`if` / `as` / `from`, unset fields left out), are in share strings, and ride along
  on import.
- **Area validation and clamping.** An area must *start* inside the page grid (`row <= rows`, `col <= cols`; spans
  at least 1); it may run past the right or bottom edge. Every consumer clamps it to the grid it draws on
  (`clamp_area`), so `{"row": 1, "col": 1, "rows": 96, "cols": 128}` means "the whole board" on every size.
  Plugin demo pages (manifest `demo.<device>.canvases`) use this so one demo fits any board.
- **Retarget.** A size change that does not send `canvases` scales the stored areas (`scale_area`) — the editor's
  retarget, an LED board's text-size switch and a FiestaPanel re-fit (both via `retarget_pages`).
- **Text.** `flow` canvases give `render_lines(..., free_spans=...)` per-row spans; wrapping lines fill them in
  reading order (whole rendered line, words never split unless no later span can hold them), alignment is per
  span, lines without wrap take their row's first span and clip. Then every covered cell is blanked
  (`TemplateEngine.blank_cells`; extended markup via `markup.blank_tiles`) on every board and page type.
- **Layers.** For a display whose `DisplayProfile.supports("pixels")` (`width` / `height` set from a `pixels`
  model), `PageService.render_page` draws the canvases on `grid_layout(width, height, font)` with the page's
  template context into `DisplayResult.layers` (+ `canvas_issues`). The fetch set (`page_plugin_ids`) includes
  plugin roots the canvases name (a formula makes it fetch-all). `DisplayResult.content_key()` (text plus a layer
  digest) is the engine's dedupe / in-flight key, so a canvas change alone is resent. The display-agnostic preview
  cache never holds layers.
- **`"format": "canvas"`** plugin variables reach a canvas `source` as the plugin's native dict; in a template line
  they render as empty text.
- **LED renderer.** `layout_message(..., layers=)` / `layout_cells(..., layers=)`, `LedLayout.layers`, `"bitmap"`
  ops after all cell ops, and the FiestaUI#343 rules (overwrite on alpha > 0, clip, monochrome luma rule; flip /
  cascade switch layers half-way and repaint them over half-flaps). Pinned by FiestaUI's 4 layer goldens in the
  vendored `tests/fixtures/fiestaui/led-golden.json` (FiestaUI 8.4.0), checked with every other golden case.
- **Output plugins.** Rich frames are `RichCells` (a `list` with `.layers`); `write_cells` and `write_transition`
  (before and after) receive them; `FrameCache` equality and the last-frame store include layers. An LED output
  plugin draws them with `layout_message(frame, spec, options, layers=getattr(frame, "layers", ()))`. Split-flap
  outputs get no rich cells, so never any layers.
- **APIs.** `layers: [{x, y, width, height, rgba}]` (+ `canvas_issues`) on the batch preview for a pixel board, on
  `POST /pages/{id}/send` (null for other boards), on `GET /board/current-message` and `GET /v1/boards/{board}` for
  a pixel board. The web passes them to `DevicePreview`, which hands them to FiestaUI's `DisplayPreview` (8.4.0+).

## 11. What core PR 4 implements — MCP / AI

- **MCP page tools.** `create_page` / `update_page` take `canvases` (validated by `PageCreate` / `PageUpdate`;
  on update a list replaces every canvas and `[]` removes them, stored as `null`). `get_page` / `list_pages`
  return them in their JSON form (`if` / `as` / `from`).
- **`render_page_preview(canvases=…)`** renders an unsaved template page through `PageService.render_page`, so
  text flows around or is blanked under the canvases exactly as a saved page. For a pixel `board_id` it adds
  `layer_count`, `layers` (`{x, y, width, height}` only) and `canvas_issues`; `include_layer_pixels=True` adds
  each layer's base64 `rgba`. Other boards answer `layers: null`.
- **`validate_template(canvases=…)`** reports each canvas problem as `{path, message}`
  (`canvases[0].content.shapes[2].fill`; a shape's `type` tag is left out of the path), plus the
  8-per-page, unique-id and area-starts-inside-the-grid checks (rows only for flagship / note).
- **AI teaching.** `POST /pages/ai/chat` takes `board_id`; the board's `DisplayProfile` reaches
  `build_prompt(display=…)`. An LED board's `ai_brief()` (lowercase, colours, hex, icons) replaces the
  Vestaboard character rules; a pixel board's chat also gets `CANVAS_RULES` (JSON shape, area / bleed / scale /
  text flow, shapes, expressions / `if` / `foreach`, plugin `source`). The generate mode never teaches canvases
  (its output schema has none). No board, an unknown board, or a split-flap board: the Vestaboard rules as before.
  The web chat sends `board_id` (the sidebar's current board) on every turn.

## 12. What core PR 4 implements — web editor

- **Where.** `web/src/components/canvas-editor/` (`CanvasesPanel`, `CanvasAreaPicker`, `CanvasDrawTab` +
  `PixelPad`, `CanvasShapesEditor`, `CanvasSourcePicker`) and `web/src/lib/canvas-editing.ts` (placement mirror of
  `canvas_placement`, pixel grid ⇄ `pixels` + `palette`, flood fill, canvas-source variables). The page builder
  shows the panel only when its preview board's model is an LED pixel matrix (`pixelBoardOf`); on any other board
  a page with canvases shows a notice, and the canvases are kept and saved unchanged.
- **Preview.** The editor previews unsaved work, so it does not use the batch preview (saved pages only):
  `POST /templates/render` takes `canvases` and renders a transient template page through
  `PageService.render_page` (flow / hide, blanked cells; `layers` + `canvas_issues` for a pixel `board_id`; a bad
  canvas is a 422 whose message the panel shows). Canvases are sent only when there are some, so every other
  render request is unchanged. Layers reach `DevicePreview`, which draws them over the cells.
- **Draw.** The pad is the content's `size` (else the canvas's pixel size on the board, capped at 128). Painting
  re-encodes the whole grid: a colour keeps the palette key it had, new colours take free keys, unused keys are
  dropped, more than 62 colours is refused, and `size` is pinned so a later area change scales the drawing. The pad
  edits `pixels` only; shapes and the background draw under them on the board but not on the pad.
- **Variables.** `GET /v1/variables` `variable_metadata` entries carry `format` when it is not `"text"`; the
  Source tab lists the `"canvas"` ones.
- **Raw view.** The plain-text editor shows `{canvas:<id>}` beside a canvas's first row (`lineMarkers`); it is
  never written into the template.
