# Flexible pages: one page, any display, styled by the user

Status: approved for local build (not pushed) · 2026-10-28

## Intent

FiestaBoard is becoming a platform for many kinds of display: split-flap boards, LED matrices of every size (Divoom Pixoo 64×64, AWTRIX/Ulanzi 32×8, HUB75 64×32 to 128×64, Tidbyt, WLED, MAX7219, P10), and LED-style TV panels. Users want to change how their LED pages look: **font face, font size and colours to start, and more over time** as the platform grows. A page should keep working when a user changes a font, moves it to a different display, or buys a new one.

Today none of that holds. Every page is pinned to one exact character grid (`size_key`, `src/devices.py:731`), and a board only shows pages whose grid matches exactly (`pages_compatible_with_board`, `src/devices.py:886`). On LED boards the grid comes from the board's single font (`output_config.font`, `src/outputs/board_profile.py:215`), so changing the text size on a Pixoo turns its 10×16 pages into pages that don't fit an 8×10 board. That is the bug users have already hit. Nothing on a page can say "this line bigger" or "this font": the only page-level styling is inline colour markup.

The fix is to separate three things that are welded together today:

1. **Content**: what the page says: lines of text with variables, formulas and icons, plus art.
2. **Style**: how it should look: font, size, colour, alignment. These are requests, not guarantees.
3. **Layout and rendering**: how it lands on a particular board. This is worked out per board at render time, from what that board can actually do.

A page written once then renders on every board, using each board's real capabilities, and says clearly where it had to compromise.

## Goals

- A new kind of page, a **flexible page**, that is not tied to a grid and renders on any board: LED boards of any size and font, TV panels, and split-flap boards.
- **Per-page and per-line styling** on LED boards: font face, font size, text colour, background colour, alignment, letter case, and what to do when text doesn't fit.
- **Board-level style defaults**, such as a board's default font and default text colour. These fill a real gap: nothing in core sets a text colour today; `LedLayoutOptions.text_color` exists but is never set.
- A **style vocabulary that can grow** without new page formats: new properties and new fonts are added as data, and older software keeps unknown properties intact.
- **Honest fitting**: when a style can't be honoured or content doesn't fit, the render reports it, in the same spirit as today's `charset_issues`. No silent cropping (#1748).
- **Existing pages keep working exactly as they do**, and can be converted to flexible pages on request.
- Designed so **positioned areas** ("canvas-like regions that place data") can be added later without another format change.

## Non-goals (for this project)

- **Positioning.** No free placement of blocks or regions yet. The format reserves room for it (see "Room for positioning"), but the only layout built now is a vertical stack.
- **Outline (TTF/OTF) fonts.** Faces stay bitmap fonts. The font registry is shaped so outline fonts can be added later for TV panels.
- **Device-native text engines**, such as AWTRIX's own text rendering. FiestaBoard keeps drawing the pixels.
- Per-block animation or transitions.
- New styling on split-flap boards beyond what the hardware can do (colour tiles, one font).
- Retiring grid pages. They stay as a first-class page kind.

## Anti-goals: failure even if it technically works

- A user's existing pages, schedules or collections break, or look different, without them choosing to convert.
- Existing output plugins (`output_api` 1, including community ones such as rummeyer's Ulanzi TC002) stop working or must be updated just to show flexible pages.
- Content is cropped or dropped without the user being told where and why.
- A **third** implementation of LED text layout. Core already has a Python port of FiestaUI's `led-matrix.ts` held to golden fixtures; a flexible-page layout engine must not spawn yet another copy that drifts.
- Users end up maintaining **per-device copies** of the same page.
- Fiestabot still has to do character-width arithmetic to write a page that fits.

## What exists today that this builds on (verified on `origin/main` ff2415c4a)

- **`DisplayProfile`** (`src/outputs/display_profile.py:41`) already describes a board: technology, colour model (tiles/rgb/mono), font, pixel width and height, charset coverage, and `supports()` for lowercase, colour text, background, tiles, icons, rgb, pixels. It is the natural "what can this board do" input to layout.
- **`BoardContext.key`** includes `display.key`, so plugin data and render caches are already per display, not just per grid.
- **Pixel layers.** Rich/custom-charset outputs already receive `RichCells` with `.layers` (`CanvasLayer(x, y, w, h, rgba)` in board pixels), painted over the cells by the output's `layout_message` (`src/led/matrix.py:732-738`). The Pixoo and Ulanzi plugins both rasterise through core's `src/led` and composite layers. FiestaUI's `DisplayPreview` draws layers too.
- **Canvases** (`src/canvas/`) are positioned areas bound to data via `source`, with a shape model (rect, circle, text, gradient, pixels). They are anchored to character cells; free placement was explicitly deferred (`docs/internal/reference/PIXEL_CANVAS.md` §8).
- **The template engine** expands variables, formulas, colour tiles, icons and extended markup (`{{red:HOT}}`, `{{#rrggbb:x}}`, `{{icon:sun}}`) line by line (`src/templates/engine.py`).
- **Fonts**: exactly two bitmap faces, 3x5 and 5x7 (`src/fiestaui/led-fonts.json`, vendored verbatim from FiestaUI's `lib/led-fonts.ts`, pinned in `src/fiestaui/provenance.json`).
- **Storage** is versioned JSON with migrations (`src/pages/storage.py`, `CURRENT_SCHEMA_VERSION = 6`). `Page` is an `ExtensibleDocument` (`extra="allow"`), so unknown fields survive saves. The public API follows "deprecation, never deletion" (`docs/internal/reference/API_CONVENTIONS.md`).

## The design

### 1. Two kinds of page

- **Grid pages**: every page that exists today (`template`, `composite`, `single`). They are unchanged: exact grid, exact fit, same editor, same API.
- **Flexible pages**: a new page `type: "flexible"`. There is no `device_type`, `grid_rows`/`grid_cols` or `template[]`. A flexible page **fits every board**. The board picker, schedule and collections accept it anywhere, subject to an optional `targets` restriction (below).

Grid pages remain the right tool for split-flap owners who want exact control and for pixel-perfect art. Flexible pages are the default for new LED pages once the editor ships.

### 2. The flexible page document

```jsonc
{
  "type": "flexible",
  "name": "Morning",
  "style": { "font": "fiesta", "size": "medium", "color": "#ffffff" },  // page defaults
  "layout": {
    "kind": "stack",          // the only kind built now; see "Room for positioning"
    "valign": "middle",       // top | middle | bottom | spread
    "gap": "small"
  },
  "blocks": [
    { "id": "b1", "kind": "text", "text": "{{date_time.time}}",
      "style": { "size": "large", "color": "{{weather.temp_color}}", "align": "center" },
      "priority": 1 },
    { "id": "b2", "kind": "text", "text": "{sun} {{weather.temp}}° {{weather.summary}}",
      "style": { "align": "center", "overflow": "wrap" }, "priority": 2 },
    { "id": "b3", "kind": "canvas", "canvas": { /* today's CanvasContent or source */ },
      "style": { "height": "fill" }, "priority": 3 }
  ],
  "targets": null              // optional: restrict to technologies or boards
}
```

- **Blocks** are the content units. v1 kinds:
  - **`text`**: one logical line. Its `text` uses **exactly today's template line syntax**: variables, formulas, filters, colour markup, icons and extended markup all keep working, and the existing engine expands them. Unlike a grid line, its width is not counted in characters; layout measures it in the font it ends up in.
  - **`canvas`**: today's `CanvasContent`/`source` (shapes, pixels, AI art), sized by layout rather than by a cell area.
  - **`spacer`**: vertical space.
  - Further kinds (icon row, progress bar, image) can be added later.
- **`priority`** says what to drop first when a small display can't fit everything. A lower number is more important.
- **Conditional blocks.** A block may carry an `if` expression using the formula syntax, so a block only shows when, say, a plugin has data. This uses the same evaluator canvases already use.
- **`targets`** (optional) restricts where the page may be scheduled, for example `{"technology": ["led_matrix"]}` or a list of board ids. It is for the rare page that only makes sense on one kind of display.
- **Unknown block kinds and style properties are preserved.** This rides on `ExtensibleDocument`. Old software keeps the data and renders the parts it understands, reporting the rest as unsupported.

### 3. Style: requested properties, resolved per board

**The cascade, lowest to highest:** device model defaults → **board style** (new, per board, set by the user) → page `style` → block `style`.

**v1 properties:**

| Property | Values | Notes |
|---|---|---|
| `font` | a font family id from the registry | v1 has one family, `fiesta` (today's two faces); more arrive as data |
| `size` | `small` · `medium` · `large` · `xlarge` · `fit` · an exact pixel height | Named sizes map to a pixel height through a scale defined relative to the board's surface. `fit` takes the largest size that fits the block's text on one line. |
| `color`, `background` | named board colour, `#rrggbb`, or a `{{…}}` expression | Expressions allow data-driven colour (a temperature colour). |
| `align` | `left` · `center` · `right` | |
| `case` | `as-is` · `upper` · `lower` | |
| `overflow` | `wrap` · `shrink` · `ellipsis` · `scroll` (reserved) | What to do when a block is too wide. `scroll` is reserved for animated displays and not built in v1. |
| `height` (canvas and spacer only) | `auto` · `fill` · a pixel or fractional value | |

Page-level `layout` takes `valign` and `gap`.

**Style values are requests.** The resolver turns them into something this board can show, and records every compromise as a **style issue**:

- **Font**: the requested family, else the board style's family, else the device default.
- **Size**: pick the family's face at the requested pixel height. If there is none, use the nearest smaller face at an **integer scale** (×2, ×3), which gives large text immediately with no new glyph data. If even the smallest face is too big, report it.
- **Colour**: on `rgb` boards, as given. On `monochrome` boards, the panel colour: any non-black colour counts as lit, so contrast is preserved. On `tiles` boards (split-flap), the nearest of the 8 board colours for backgrounds and tiles; text colour is dropped (report).
- **Case**: `lower` on an uppercase-only charset is reported and rendered upper.

**Board style** is a new per-board setting (default font, default size, text colour, background), shown in board settings for any board whose display supports it.

- It is **owned by core** and stored on the board, not inside the output plugin's `output_config`, so no output plugin changes or re-pins are needed.
- The Pixoo's existing "Text size" setting (the Divoom plugin's own `font` setting, read via `output_config.font`) stays where it is and keeps setting the board's grid for **grid pages**. When the user hasn't set a board style size, the board's default size is **derived from it** (3x5 → the 5 px size, 5x7 → the 7 px size).
- **Board text colour and background apply to grid pages too.** Unset, they are today's white on black, so nothing changes until a user sets them, and setting one is the user's choice. This wires `LedLayoutOptions.text_color` through `led_layout_options()`, which today never sets it.

### 4. Fonts become a registry

- The font registry (today `led-fonts.json`) becomes a list of **families**, each with one or more bitmap **faces** at given pixel heights. Each face carries glyph cell size, spacing and coverage.
  - Today's two faces become **one family, `fiesta`, at two sizes**: the 3x5 face (5 px tall) and the 5x7 face (7 px tall). Small/Large is therefore a **size**, not a font, which matches what users already call it.
  - **Phase 1 is core-only.** Core defines the family as a thin mapping over the faces it already vendors (face ids `3x5` and `5x7` are unchanged, so `device-model.schema.json`, `layoutOptions.font` and the vendored files' hashes stay as they are). Moving family definitions into FiestaUI's data is done in phase 7, when the first genuinely new face arrives.
  - New faces and families (a 4x6, a bold 6x8, a tall 8x12 numeral face, an outline face later) are **data additions**, not format changes.
- FiestaUI stays the **single source of glyph data**. New faces are added there first and vendored into core with the existing provenance and golden-fixture process. Core and the UI must never disagree on a glyph.
- Plugins can still bring custom glyphs through charsets, as today.
- The registry entry for a face has a `kind` (`bitmap` now, `outline` reserved). The resolver never assumes bitmap beyond the faces it is given.

### 5. Layout runs on the server, once, per board

A new **flexible layout engine** in core (`src/layout/`, name the builder's call):

1. **Expand.** Each block's text goes through the existing template engine's **expansion** (variables, formulas, filters, colours, icons, extended markup) against the board's context (same caching, same `BoardContext.key`), producing markup tokens. It does **not** go through the engine's grid render (`render_lines`: padding, alignment, cropping, spill), which counts in tiles.
   - Width-dependent markup (`{{fill_space}}`, `{{fill_space_repeat:X}}`, `{{filled:X}}`) is emitted as an **unresolved fill marker** and filled by the layout engine in pixels at step 4, so it keeps working.
   - Plugins are fetched with the **board's** `BoardContext` (its current grid and display), not a page geometry; a flexible page has none.
2. **Resolve styles** for the board (section 3).
3. **Measure** each token run in its resolved face, in **pixels**. Glyph advance comes from the face, and icons and tiles have fixed advances.
4. **Fit** each block across the surface width using its `overflow` rule. `wrap` breaks at spaces, then mid-word. `shrink` steps down faces, then scales. `ellipsis` cuts at a glyph boundary and adds `…` or `.`.
5. **Stack** blocks vertically with `gap`. If the total is too tall, drop blocks from the lowest priority upward (report each one), then apply `valign`.
6. **Emit**:
   - **LED and pixel boards: a full-frame pixel image.** Glyphs are drawn with the **existing** `src/led` rasteriser primitives, extended to accept a face per run. This is not a new rasteriser. Canvas blocks go through the existing `render_content`/`fit_nearest`/`upscale`.
   - **Split-flap and integer-only boards: a cell grid.** Each block is laid out in the board's one character size, wrapped by characters, with colour mapped to tiles. This is what makes flexible pages run everywhere. The output is an ordinary 0–71 grid, so nothing downstream changes.
7. **Report**: a `layout_issues` list (style compromises, wrapped or shrunk blocks, dropped blocks, ellipsised text), returned with every preview and stored with the last render for the board.

The layout engine lives **only in Python**. FiestaUI never lays out flexible pages; it draws the frame the server produced (see "Previews"). That is what keeps us at the two layout implementations we have today and stops a third.

### 6. Delivery to outputs without breaking any plugin

**Phase 1: ride the existing layers path.** For a flexible page on a pixel board, core sends `RichCells` whose `.layers` holds **one full-frame, opaque layer**: the rendered image at `(0, 0, width, height)`. Every rich-charset output already paints layers last, over the cells, so the Pixoo and the Ulanzi plugin show flexible pages with **no plugin change**.

- **The cells and the 0–71 grid are not blank.** They carry the page's **text layout at the board's current grid** (the same cell layout split-flap boards get, section 5 step 6). It is hidden under the opaque frame on the device, but board state and readback, the duplicate-frame check (`matches_frame`), preview text alternatives, Fiestabot's "what's on the board" and `/v1` clients all keep seeing real text. This means the cell layout ships in **phase 1**, not later.
- Builder must verify this per output, including FiestaPanel's LED viewer, which draws the 0–71 grid itself (`markup_follows_charset=False`). Any output that can't show layers keeps showing grid pages only and is excluded by the fit check, with a reason.
- **Transitions.** Per-pixel LED transitions (slide, wipe, fade, dissolve) work unchanged on frames. Per-cell ones (flip, cascade) need a cell grid; for flexible pages they fall back to `fade`. **Transition plugins** (`plugin_type: "transition"`: typewriter, slot_machine, simple_dissolve) step integer grids, so on a pixel board showing a flexible page they also fall back to `fade`. Both fallbacks are shown in board settings and the page's transition picker, not silently ignored. On split-flap boards, flexible pages produce an ordinary grid, so every transition works as today.
- **Phase 2 (later, optional): `output_api` 2** adds an explicit `write_frame(RGB frame)` and a capability declaration (surface, colour model, allowed fonts, whether a font choice changes device bytes). This is cleaner than a fake layer, but nothing in this project depends on it, so community plugins are never forced to move.
- The render short-circuit and dedupe keep working. The fingerprint is still "the page document + the referenced plugin data + config + display key", and the content key becomes a digest of the frame.

### 7. Fit, scheduling and the small-display floor

**Grid pages on LED boards carry their own text size.** This replaces "the board's text size decides which pages fit", which is what hid the user's Divoom pages.

- An LED board can produce one grid per text size it allows. A Pixoo 64 gives 10×16 at the 5 px size and 8×10 at the 7 px size.
- A grid page **fits an LED board if its grid is any grid the board can produce**. The page renders at the size that produces its grid: a 10×16 page draws in small text, an 8×10 page in large text, on the same board, with nothing hidden.
- **Delivery reuses the full-frame path from section 6.** Core rasterises the page at its own size into one opaque full-frame layer. The cells under it carry the page text projected to the board's current grid, so text readers keep working.
  - This needs no output plugin change. Verified against the Divoom plugin (`origin/main` bccc3e9): it fixes its renderer once per instance from `led_layout_options()` (`__init__.py:447`), but draws `frame.layers` over the text through core's `layout_message` (`:460-463`).
  - A grid page at the board's own current size keeps today's path unchanged, cells only.
- **The board's "Text size" setting becomes a default**: the size new grid pages are created at, and the board-style default size for flexible pages. It no longer hides anything. Board settings should say so.
- **Pages that still don't fit are flagged, not hidden.** A grid page whose grid this board can't produce at any size, such as a Flagship page on a Pixoo, appears in the page picker, schedule and Pages list greyed out with a plain reason ("Made for a 6×22 board"). It still can't be scheduled on that board. Size changes that leave pages behind are listed in board settings, not only logged.
- **Split-flap and TV split-flap boards** keep exact-grid fit, unchanged.

- `pages_compatible_with_board` returns true for any flexible page, unless `targets` excludes the board or the board's output can't receive frames or cells.
- The 3×10 minimum applies to **grid pages only**. Flexible pages could render on a 32×8 strip (one line). Actually allowing such boards to be created is out of scope, but nothing in this design should hard-code the floor into the flexible path.
- **Changing a board's text size or font never invalidates a flexible page.**

### 8. Previews and the editor

- **Previews** use the existing server-rendered preview routes (`POST /pages/{id}/preview`, `/pages/preview/batch`, and the unsaved-page render route). For flexible pages they return the frame as a layer (LED) or cells (split-flap), plus `layout_issues`. FiestaUI's `DisplayPreview` already draws both. **No layout code in the browser.**
- **The editor** for flexible pages is a new block editor:
  - a list of blocks, each a text field using the existing TipTap variable, colour and icon nodes, with a compact style bar (font, size, colour, align, overflow);
  - page style and layout settings;
  - a **multi-board preview strip** showing the page on each of the user's boards and generic models (Pixoo 64, 32×8 strip, Flagship) at once, with `layout_issues` shown under each board.

  The existing grid editor stays for grid pages.
- Creating a page asks "Flexible (any display)" or "Exact grid". The builder decides the default by board type, but LED boards should default to flexible.

### 9. Fiestabot

- New tools `create_flexible_page` and `update_flexible_page` take blocks and styles directly. Their descriptions say plainly that **no width counting is needed**: the server lays the page out and returns per-board `layout_issues` that Fiestabot can act on, for example "drop priority 3 or use `shrink`".
- `render_page_preview` and `preview_saved_page` return per-board issues for flexible pages.
- A `convert_page_to_flexible` tool (section 10) lets Fiestabot fix the "my pages disappeared" situation in one call per page, or in bulk.
- The prompt teaches the style vocabulary through the board's capabilities (`DisplayProfile.ai_brief()` extended with fonts and sizes), so Fiestabot only offers styles a board can show.

### 10. Converting existing pages (deferred: not built in this project)

Grid pages on LED boards now render at their own size (section 7), so nothing *needs* converting. Whether to offer conversion at all is decided after flexible pages have been used for a while. If it is built, this is the intended shape:

- **"Convert to flexible page"** on any template page creates a new flexible page by default, leaving the original untouched; in-place conversion is an option. The mapping:
  - each template line becomes one `text` block, keeping its markup;
  - `line_metadata` alignment and wrap become block `align` and `overflow: wrap`;
  - blank leading or trailing lines become `valign` or spacers;
  - canvases become `canvas` blocks in the order of their rows.
- The conversion reports anything that doesn't map cleanly. For example, a line that used spaces for column alignment would lose those columns, so the user can review it.
- **Bulk convert** is offered wherever grid pages don't fit a board (the "Doesn't fit" state from the Divoom text-size fix, option C). It is also available from the Pages list and through Fiestabot.
- **No automatic conversion.** Users choose.
- Composite and single pages are not convertible in v1 (Fiestabot can't author them today either). They are reported as "can't convert yet".

### 11. Storage, API and compatibility

- **Schema v7** adds the `flexible` page type with `style`, `layout`, `blocks` and `targets`. The migration from v6 is a no-op for existing pages; the version bump exists so older builds refuse a file containing flexible pages rather than mangle it (`JsonStore` refuses newer files).
- **`/v1/pages`** accepts and returns flexible pages. This is additive, so the deprecation rule is respected.
  - Existing clients that list pages will see `type: "flexible"` without `template`; that is documented in the API changelog.
  - The **share string** envelope gains flexible pages under the same `SHARE_VERSION`, or a bump, at the builder's call. Importing a flexible page into an older build must fail with a clear "needs a newer FiestaBoard" message.
- `edit_protocol` (revisions) is unchanged. `document_protocol` becomes `page-document-v2` for flexible pages only.

## Room for positioning (designed for, not built)

The user's direction: "sometimes having 'canvas' like areas that position data".

- `layout.kind` is the extension point. `stack` is built now. A later `regions` kind will hold a list of **regions**, each with:
  - an area in **surface-relative units** (fractions of width and height, or pixels with anchors), never character cells, so regions survive across displays;
  - its own nested `stack` of blocks and its own style.
- Today's cell-anchored canvases map onto this naturally: a canvas becomes a region containing a canvas block.
- **Constraints the v1 build must keep so this stays easy:**
  - blocks never store absolute positions;
  - the layout engine's stack step is a function **(blocks, styles, rect) → frame** over an arbitrary rectangle, not the whole surface, so regions can call it per area;
  - `layout_issues` carry a path (region, then block) and not just a block id.

## Constraints

- Existing grid pages, schedules, collections, share strings and `/v1` clients behave exactly as before.
- Output plugins on `output_api` 1 keep working with no changes, and should show flexible pages wherever they already composite layers.
- One source of glyph data (FiestaUI), vendored with provenance. Layout for flexible pages runs in core only.
- Golden fixtures for flexible layout per representative device: Pixoo 64 at both default sizes, 32×8 strip, HUB75 64×32, FiestaPanel LED 192×96, monochrome MAX7219, Vestaboard Flagship as cells. These fixtures are the contract.
- **Every geometry call site must route flexible pages explicitly.** `geometry_of()` (`src/devices.py:854`) and `Page.device_type` default a missing device type to `flagship`, and about 18 modules call `geometry_of`, `size_key` or `pages_compatible_with_board` (main.py, board_guards, mcp_server, v1 routes, retarget, ai/prompt_builder and others). A flexible page reaching any of them would silently be treated as a 6×22 grid page. Phase 1 must make that impossible (for example, `geometry_of` raising for a flexible page) and cover each call site with a test.
- Renders stay within today's per-tick budget on a Raspberry Pi. Layout is pure CPU on short text; cache resolved faces and measured runs.
- Repo rules apply: PRs to `main`, the commit trailer per `CLAUDE.md`, and tests first.

## Decisions made in this document (my calls, for review)

1. Flexible pages are a **new page type** rather than options bolted onto template pages, because template pages are grid-indexed through and through.
2. Block text **reuses today's template line syntax** unchanged.
3. Flexible pages **also render on split-flap boards**, laid out into the board's grid, so "any display" is literally true.
4. **Layout is server-only.** The browser draws frames.
5. **Delivery rides the existing full-frame layer path** first, and `output_api` 2 is deferred.
6. Named sizes plus `fit` plus exact pixels. Larger sizes come first from **integer scaling** of existing faces, then from new faces as data.
7. **Conversion is deferred.** Grid pages render at their own size on LED boards instead (section 7). If conversion is built later, it copies by default and is never automatic.
8. Per-cell LED transitions and transition plugins **fall back to fade** for flexible pages on pixel boards.
9. Today's two faces are **one family at two sizes**. The family mapping is core-side in phase 1, so FiestaUI isn't on the critical path.
10. Board style is **core-owned**. The Pixoo's Text size stays the plugin's setting and seeds the board's default size.
11. Board text colour and background **also apply to grid pages**. They are unset by default, so nothing changes until a user sets them.
12. On LED boards, flexible pages also fill the **cell grid with real text** under the frame, so everything that reads board text keeps working.
13. `fill_space` and friends become **pixel fill markers** resolved by layout.
14. **The board's text size is a default, not a filter.** Grid pages that this board can't produce at any size are flagged, never hidden.

## Left to the builder

- Module layout, class names, and how `PageService.render_page` dispatches to the new engine.
- The named-size scale (the pixel heights `small` to `xlarge` map to per surface), proposed from the golden devices.
- Wrap and break rules in detail (breaking inside variables, icon advance, kerning: none in v1).
- Whether the full-frame layer is one layer or one per block.
- How `layout_issues` are persisted per board and surfaced in board status.
- Editor visual design within FiestaUI components (no accent rails).
- The share-string version decision.

## Suggested phasing (for the plan)

The plan should break this into independent, testable PRs. Phases 2 to 6 can be partly parallel once phase 1 has landed.

0. **Grid pages at their own size on LED boards** (section 7): full-frame layer delivery, the any-producible-grid fit rule, the flagged "doesn't fit" state, and size changes reported in board settings. This fixes the Divoom text-size problem on its own, and phase 1 builds on its delivery path.
1. **Core model and LED layout.** Schema v7, the flexible page model and API, style resolver, font registry as families (today's two faces, plus integer scaling), the layout engine for pixel boards, full-frame layer delivery, fit rules, `layout_issues`, golden fixtures.
2. **Split-flap layout** for flexible pages.
3. **Board style settings**, wired into the cascade, with the Pixoo text-size setting re-expressed as the default size.
4. **Editor and multi-board preview** (web, plus FiestaUI components if needed).
5. **Fiestabot tools and prompt.**
6. ~~Conversion~~: deferred (section 10).
7. **New faces**, starting with a FiestaUI PR that adds a font family, to prove "fonts are data".
8. (Later) `output_api` 2 frame delivery and the capability declaration; `regions` layout.
