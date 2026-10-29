# Small LED boards, and the Ulanzi TC001

Date: 2026-10-28
Status: awaiting owner approval

## Intent

FiestaBoard wants to drive any display it can. The Ulanzi TC001 — a 32 × 8
RGB pixel clock — cannot be added today, and FiestaBoard is the reason: core
refuses an LED board measured in pixels below 3 rows × 10 columns
(`MIN_LED_GRID_*`, `src/devices.py`). In the 3x5 face a 32 × 8 panel fits
1 row × 8 columns; in 5x7, 1 × 5. The firmware is not the obstacle — AWTRIX NG
runs on the TC001 with the same `/api/v1` as the TC002.

So this is two pieces of work:

1. **Core:** let an LED board in pixels be as small as one row, so a panel
   like the TC001 can be a board.
2. **Plugin:** a new first-party output plugin,
   `fiestaboard-output--ulanzi-tc001`, hosted in the FiestaBoard org, that
   shows pages on a TC001 running AWTRIX NG.

## Goals

- A TC001 can be added as a board, tested, and shows pages and canvases.
- The floor change is general: any small pixel matrix benefits, not only the
  TC001.
- On the TC001 the owner picks the text size, like the Pixoo's switch:
  **3x5 — 1 row of 8** (default) or **5x7 — 1 row of 5**, which fills the
  panel's height (7 of 8 rows lit) for a bolder, larger read.
- Canvas pages use all 32 × 8 pixels.
- The page editor, preview and page-list filter work for a 1-row board as
  they do for the TC002's 3-row one.

## Non-goals

- A new font. A 3x3 face was mocked up on a 32 × 8 grid and rejected: `5`/`S`
  and `9`/`Q` become the same glyph and short words stop reading. No FiestaUI
  font work is needed.
- Fitting 3-row pages onto the TC001 (cycling rows, scrolling a long row).
  Possibly a later plugin setting; not now. Pages for the TC001 are made for
  its 1-row size, as TC002 pages are made for 3 × 13.
- AWTRIX 3, or Ulanzi's stock firmware. AWTRIX NG only, as the TC002 plugin.
- Changing the community TC002 plugin.

## Anti-goals

- Quietly inflating a small board to a bigger grid and cropping every frame on
  the device (what `clamp_grid` would do without the floor check — the very
  failure `src/outputs/geometry.py`'s docstring warns about).
- Lowering the floor for Vestaboards, FiestaPanels, TVs, or any model other than
  LED-in-pixels. Their 3 × 15 Note floor stays.
- A preview in FiestaBoard that does not match what the clock shows.

## Constraints

- The floor is mirrored in three places that must agree: `src/devices.py`
  (`MIN_LED_GRID_*`, `ABSOLUTE_MIN_GRID_*`), `src/outputs/geometry.py`
  (`grid_floor`, `check_floor`, docstrings), and `web/src/lib/board-dimensions.ts`.
  `ABSOLUTE_MIN_GRID_*` also bounds page and template geometry
  (`src/pages/models.py`, `src/templates/models.py`, `src/settings/routes.py`).
- `src/outputs/conformance.py` exports `MIN_LED_ROWS`/`MIN_LED_COLS` to every
  output plugin's test suite; plugins import them.
- Output plugins need FiestaBoard ≥ the release that carries the floor change;
  the plugin's `fiestaboard_version` says so.
- PRs target `main`. FiestaBoard org is on GitHub Free.

## Decided

- **Option A** of the mockup: the existing 3x5 face, one row of 8 — chosen by
  the owner. The owner wants the panel's height used, hence the 5x7 choice
  alongside it.
- **New plugin hosted in the FiestaBoard org**
  (`Fiestaboard/fiestaboard-output--ulanzi-tc001`), not a change to the
  community TC002 plugin.
- **Marketplace only** — chosen by the owner. Listed in `plugin-registry.json`
  (and `plugin-previews.json`) as `ulanzi_tc002` is; installed from
  Displays → Marketplace. Not in `FIRST_PARTY_OUTPUTS`, not pinned in
  `outputs.lock.json` (Divoom Pixoo, Vestaboard and FiestaPanel are), so no
  image or registry-trust changes. Its `fiestaboard_version` is the first
  release carrying the floor change, and the registry entry lands once that
  release is out.
- **Floor for an LED board in pixels: 1 row × 5 columns** (my call). One row
  is the TC001's reality. Five columns is the TC001 at 5x7 and keeps a single
  word legible; a narrower matrix is not a display FiestaBoard pages can serve
  meaningfully. All other models keep 3 × 15.
- **Other small pixel models become valid boards too, on purpose** (my call,
  following "support any and every display"): FiestaUI's
  `ulanzi_tc001_awtrix` (1 × 8), `max7219_4in1` (1 × 8) and `p10_hub12_32x16`
  (2 × 5), which `tests/test_outputs_board_create.py` pins as refused today.
  Those tests flip to "created"; a pixel model below 1 × 5 is the new refused
  case. The anti-goal above is about non-pixel models only.
- **The device check is not a gate** (my call): core and the plugin are built
  against the mock clock now; the on-device checks below gate the plugin's
  first release, not its development.

## The plugin, as far as it is settled

Modelled on the TC002 plugin (MIT; credit it in the README):

- Device model `ulanzi_tc001`: `pixels` geometry 32 × 8, `charset` `led_3x5`,
  `font` `3x5`, `layoutOptions.font.allowed` `["3x5", "5x7"]` default `3x5`,
  tile-gap and block-padding options as the TC002. Plain 32 × 8 — none of the
  TC002's 17-row trick (one row needs no dropped gap).
- Each frame is a pushed app (`PUT /api/v1/apps/pushed/{name}`) with **no
  layout** and one `bitmap` draw command at 0,0, 32 × 8 RGB888 base64 — about
  1 KB of JSON, under AWTRIX NG's 8192-byte JSON body limit. This differs
  from the TC002 plugin on purpose: layouts are TC002-only (the TC002
  plugin's `__init__.py`: "an ESP32 AWTRIX NG (32 x 8: no layouts)"), and the
  double-size drawing pushed apps get is the TC002's 52 × 16 → 26 × 8; an
  ESP32 panel is 8 pixels high, fixed (AWTRIX NG `docs/reference/limits.md`).
  If the device draws it scaled or refuses it, the fallback is `pixels` draw
  commands per colour run, still one request per frame. Show on change,
  display time, app name, password, Find my clock, restart detection and
  streamed transitions as the TC002 plugin.
- Test connection tells apart a TC001 from a TC002 / other AWTRIX NG clock by
  `GET /api/v1/device` `boardType` (`awtrixng` for an ESP32 build, `tc002` for
  a TC002, per the TC002 plugin) and the panel size, and says which it found.
- **Model id `ulanzi_tc001`, label "Ulanzi TC001 (AWTRIX NG)"**, declared in
  the plugin's own `output/device-models.json` as the TC002 plugin does (my
  call). FiestaUI's catalogue already has `ulanzi_tc001_awtrix` ("AWTRIX /
  Ulanzi TC001 (32×8)", AWTRIX 3 era, 2 fps, no font switch); it stays as is —
  a generic AWTRIX 3 entry, a different firmware and API. No FiestaUI PR.
- Tests run against a mock clock and FiestaBoard's conformance suite, ≥ 80 %
  coverage, CI on push.

## Left to the builder

- Every core call site that assumes ≥ 3 rows or ≥ 10 columns for an LED board
  (layout, transitions, editor, size indicator, panel scale, previews,
  the AI prompt builder's sizing hints) — find and fix them; a 1 × 5 and
  1 × 8 board must lay out, transition and preview correctly.
- Test updates: the core and web tests that pin 3 × 10 change to the new floor;
  add tests for a 1-row LED board being created, refused below 1 × 5, and its
  grid following the font switch.
- How the plugin shares code with the TC002 plugin (copy and adapt is fine; it
  is a separate repo with its own owner).

## To verify on the device

The owner has a TC001 still in its box. Before calling the plugin done:

- Flash AWTRIX NG from its web installer, note the version.
- Whether a pushed app's layout on the TC001 draws all 32 × 8 pixels.
- What `GET /api/v1/device` reports that identifies a TC001.
- Stream rate it sustains (start at the TC002's 5 fps).
