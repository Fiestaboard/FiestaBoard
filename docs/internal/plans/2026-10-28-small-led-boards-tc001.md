# Small LED Boards and the Ulanzi TC001 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an LED board measured in pixels be as small as 1 row × 5 columns, and ship a marketplace output plugin that drives a Ulanzi TC001 (32 × 8, AWTRIX NG).

**Architecture:** Core: lower `MIN_LED_GRID_*` from 3 × 10 to 1 × 5 in `src/devices.py` and its web mirror; everything that bounds by `ABSOLUTE_MIN_GRID_*` follows; sweep the LED stack for ≥ 3-row assumptions. Plugin: a new repo adapted from the MIT TC002 plugin — same AWTRIX NG `/api/v1` pushed-app transport, but a plain 32 × 8 bitmap draw with no layout and no gap-row squeeze, and a 3x5/5x7 text-size switch.

**Tech Stack:** Python 3.11, pytest (+ pytest-socket, pytest-cov); React/TypeScript + Vitest for web; AWTRIX NG HTTP API.

**Spec:** `docs/internal/specs/2026-10-28-small-led-boards-tc001-design.md`

## Global Constraints

- LED-in-pixels floor: **1 row × 5 columns**. Every non-`pixels` model keeps **3 × 15**.
- Core work on branch `feat/small-led-boards` in worktree `~/workspace/FiestaBoard-worktrees/tc001`; PR targets `main`.
- Plugin repo: local at `~/workspace/fiestaboard-output--ulanzi-tc001`, later `Fiestaboard/fiestaboard-output--ulanzi-tc001`. Do **not** create or push the GitHub repo — the coordinator does that after asking the owner.
- Plugin id `ulanzi_tc001`, name `Ulanzi TC001 (AWTRIX NG)`, device model id `ulanzi_tc001`, version `0.1.0`, `fiestaboard_version` `>=10.2.0` (first minor after 10.1.19; coordinator confirms at release).
- Marketplace only: no change to `FIRST_PARTY_OUTPUTS` or `outputs.lock.json`.
- The TC002 plugin (`a local checkout of https://github.com/rummeyer/fiestaboard-output--ulanzi-tc002`) is MIT © 2026 Oliver Rummeyer: keep that copyright line in the new LICENSE and credit it in the README.
- Never run Python or npm installs on the host. Core Python tests: the `fb-tc001-test` image (Task 1). Web tests: `docker compose -p fb-tc001 -f docker-compose.dev.yml --profile test run --rm web sh -c "npm ci --legacy-peer-deps && npx vitest run <files>"`.
- Commit trailer, exactly: `Co-Authored-By: Claude <noreply@anthropic.com>`. Never `git stash` (shared across worktrees).
- No real personal data in examples; use `192.0.2.x` addresses.

## Review Focus

1. **A 1-row board through every LED transition** (flip, slide, wipe, cascade, dissolve, fade): expect frames, no IndexError/ZeroDivision — Task 3.
2. **The font switch on a 32 × 8 model**: 3x5 → 1 × 8, 5x7 → 1 × 5; a stored board without `font` resolves by its grid — Task 3.
3. **A page or template saved at 1 × 8** validates and round-trips; 0 rows is still refused — Task 1.
4. **The bundled Vestaboard/FiestaPanel/Divoom packages' own test suites** (core CI runs them against this checkout) still pass with the new floor — Task 1 verification.
5. **A TC002 or a non-32-wide ESP32 AWTRIX NG** at the TC001 plugin's address: Test connection refuses it with a clear message instead of drawing garbage — Task 7.

---

## Track A — Core (`feat/small-led-boards`)

### Task 1: Lower the LED floor to 1 × 5 in core Python

**Files:**

- Modify: `src/devices.py:57-71` (constants + comment), `src/outputs/geometry.py` (module docstring, `grid_floor`/`resolve_content_grid` docstrings), `src/outputs/conformance.py:121-127` (comment)
- Modify: `docs/development/output-plugins.md:691`, `docs/internal/reference/ARCHITECTURE.md:355-358`
- Test: `tests/test_outputs_board_create.py`, `tests/test_page_models.py` (or the existing page-model test file — find with `grep -ln "grid_rows" tests/test_pages*.py`)

**Interfaces:**

- Produces: `MIN_LED_GRID_ROWS == 1`, `MIN_LED_GRID_COLS == 5`, `ABSOLUTE_MIN_GRID_ROWS == 1`, `ABSOLUTE_MIN_GRID_COLS == 5` (`src/devices.py`); `grid_floor(model)` returns `(1, 5)` for `pixels` models; conformance exports `MIN_LED_ROWS, MIN_LED_COLS == 1, 5`.

- [ ] **Step 0: Build the test image** (once; reused by every core task)

```bash
docker build -t fb-tc001-test -f - . <<'EOF'
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
RUN pip install -q -r requirements.txt -r requirements-dev.txt pytest-socket
EOF
```

Run tests with: `docker run --rm -v "$PWD":/app -w /app fb-tc001-test pytest <args>`. Baseline: `... pytest tests/test_outputs_board_create.py -q` → all pass.

- [ ] **Step 1: Rewrite the floor tests to the new contract (they fail)**

In `tests/test_outputs_board_create.py`:

- `test_a_32x8_awtrix_is_refused_below_the_floor` → `test_a_32x8_awtrix_is_a_1x8_board`: `resolve_content_grid(_model("ulanzi_tc001_awtrix"), None, None) == (1, 8)`.
- `test_an_led_board_below_3x10_is_still_refused` → `test_small_led_boards_clear_the_1x5_floor`, parametrized `[("ulanzi_tc001_awtrix", (1, 8)), ("max7219_4in1", (1, 8)), ("p10_hub12_32x16", (2, 5))]`, asserting the grid.
- New `test_an_led_board_below_1x5_is_refused`: a synthetic model `{"id": "tiny", "geometry": {"kind": "pixels", "width": 16, "height": 8}, "font": "5x7", "charset": "led_5x7"}` (copy the other keys from `_model("ulanzi_tc001_awtrix")`) raises `BelowFloorError` with message exactly `"Device model 'tiny' shows 1x2 characters, below the 1x5 minimum an LED board needs, so FiestaBoard cannot create a board for it."`
- New `test_a_non_pixel_model_keeps_the_note_floor`: `grid_floor(_model("vestaboard_panel")) == (3, 15)`.
- `test_an_led_board_at_5x7_clears_the_3x10_led_floor` → rename `..._clears_the_led_floor` (asserts unchanged).
- `test_a_board_below_the_floor_is_refused_and_nothing_is_saved` → post the `tiny` model instead (monkeypatch it into the builtin models the way the file's fixtures do); same 400 + nothing-saved assertions, message `... shows 1x2 characters, below the 1x5 minimum ...`.
- New `test_a_tc001_board_is_created_as_a_1x8_panel`: posting `device_model="ulanzi_tc001_awtrix"` → 2xx, stored `(device_type, grid_rows, grid_cols) == ("panel", 1, 8)`.

In the page-model test file: `test_a_page_at_1x8_validates` (`grid_rows=1, grid_cols=8` accepted) and `test_a_page_below_the_absolute_floor_is_refused` (`grid_rows=0` and `grid_cols=4` each raise `ValidationError`).

- [ ] **Step 2: Run them, confirm they fail on the 3x10 floor** — `pytest tests/test_outputs_board_create.py -q` → FAIL with "below the 3x10 minimum".

- [ ] **Step 3: Change `MIN_LED_GRID_ROWS = 1`, `MIN_LED_GRID_COLS = 5`** in `src/devices.py`; rewrite the comment above them (a 32 × 8 TC001 is 1 × 8 at 3x5, 1 × 5 at 5x7; one word is the least a page can say). Update every "3 × 10"/"3x10" in the geometry/conformance docstrings and the two doc files to 1 × 5. `grep -rn "3 × 10\|3x10\|3 x 10" src docs tests` afterwards shows only historical issue references, if any.

- [ ] **Step 4: Run** `pytest tests/test_outputs_board_create.py tests/test_outputs*.py tests/test_page*.py tests/test_template*.py tests/test_settings*.py -q` → PASS. Then the full non-integration suite: `pytest tests/ -m "not integration" -n auto -q` → PASS; fix any test that pinned 3 × 10 by updating it to the 1 × 5 contract (say which in the commit body).

- [ ] **Step 5: Bundled outputs still pass** — `python scripts/seed_outputs.py build --lock outputs.lock.json --dest /tmp/seed` then each of `vestaboard fiestapanel divoom_pixoo`: `cd /tmp/seed/$id && ./run_tests.sh /app` (all inside the container, with network for the seed build). Expected: PASS. If one pins 3 × 10, stop and report — that package needs its own PR.

- [ ] **Step 6: Commit** — `feat(outputs): lower the LED board floor to 1x5`.

### Task 2: Web mirror of the floor

**Files:**

- Modify: `web/src/lib/board-dimensions.ts:9-24,98` (constants + comments)
- Test: `web/src/__tests__/board-dimensions-panel.test.ts:30-32,58-60`, `web/src/__tests__/board-size-indicator.test.tsx:107-126`

**Interfaces:** Consumes Task 1's values. Produces TS `MIN_LED_GRID_ROWS = 1`, `MIN_LED_GRID_COLS = 5`, `ABSOLUTE_MIN_GRID_* = 1, 5`.

- [ ] **Step 1: Update tests** — floor test expects `[1, 5]` for both pairs (title "…has a 1x5 floor…"); clamp test: `resolveDimensions("panel", 1, 1, 0, 2)` → `{ rows: 1, cols: 5 }`; new `resolveDimensions("panel", 1, 1, 1, 8)` → `{ rows: 1, cols: 8 }`; size indicator: replace the 3 × 10 case with `labels a TC001's 1 × 8 grid as 1 × 8` (`"1 × 8 · Panel"`, aria-label `"1 row by 8 columns, Panel"` — check how the component pluralizes; if it says "1 rows", fix the component to singular and keep this assertion).
- [ ] **Step 2: Run, confirm FAIL** (expected `[3, 10]` vs `[1, 5]`).
- [ ] **Step 3: Change the constants and comments** to mirror `src/devices.py`.
- [ ] **Step 4: Run** the two files, then the full web suite → PASS. `grep -rn "3 × 10\|3x10\|MIN_LED" web/src` and fix any remaining 3 × 10 assumptions (e.g. `web/src/lib/panel-scale.ts:57` comment).
- [ ] **Step 5: Commit** — `feat(web): mirror the 1x5 LED board floor`.

### Task 3: A 1-row board works end to end in the LED stack

**Files:**

- Test: `tests/test_small_led_boards.py` (new)
- Modify: whatever the tests show breaking — likely in `src/led/matrix.py`, `src/led/transitions.py`, `src/outputs/board_profile.py`, `src/ai/prompt_builder.py`, page-fit/preview code; and web page editor/preview components found by `grep -rn "rows\s*[<>=-]\|\[2\]\|rows - 1" web/src/components/{pages,displays,board}*`.

**Interfaces:** Consumes Task 1. Uses `layout_message`, `rasterize`, `LedMatrixSpec` (`src/led`), `board_font`, `derived_plugin_grid` (`src/outputs`), the transition planner in `src/led/transitions.py`.

- [ ] **Step 1: Write the tests (expect some to fail)**
  - `test_a_32x8_matrix_lays_out_one_row_of_8_at_3x5` — `layout_message("SUNNY 72", LedMatrixSpec(32, 8, "3x5"))` grid is 1 × 8; `rasterize(...)` frame is 32 × 8, glyph rows at y 1–5 (centred: offset `(8-5)//2 == 1`).
  - `test_a_32x8_matrix_lays_out_one_row_of_5_at_5x7` — 1 × 5, glyphs at y 0–6.
  - `test_every_led_transition_runs_on_a_1x8_board` — parametrize over every transition id the module exports; plan from `"HELLO"` to `"WORLD"` on 32 × 8 3x5; asserts ≥ 1 frame, every frame 32 × 8 × 3 bytes, last frame equals the rasterized target.
  - `test_the_font_switch_moves_a_32x8_model_between_1x8_and_1x5` — a model like `ulanzi_tc001_awtrix` plus `layoutOptions.font = {"allowed": ["3x5", "5x7"], "default": "3x5"}`; `board_font` with `output_config.font` `"5x7"` → `"5x7"`; grid via `model_cell_grid` → `(1, 5)`; with `"3x5"` → `(1, 8)`; a board with no font and stored grid `(1, 5)` → `"5x7"`.
  - `test_a_page_longer_than_one_row_is_cut_to_the_first_row` — a 3-line message on 1 × 8: only row 0 drawn, no error.
  - `test_a_canvas_layer_covers_all_32x8_pixels` — one full-size bitmap layer on a 1 × 8 board; every pixel of the rasterized frame comes from the layer.
- [ ] **Step 2: Run, note which fail and why.**
- [ ] **Step 3: Fix each failure at its cause** (no special-casing on 1 row where general code can handle any count). Then sweep: `grep -rn "rows\s*-\s*1\|\[1\]\[\|\[2\]\|>= *3\|< *3" src/led src/outputs src/pages src/ai src/templates` and read each hit for a ≥ 3-row assumption; add a test for any real one before fixing.
- [ ] **Step 4: Web** — load a 1 × 8 panel board in the page editor preview and size indicator tests (add `web/src/__tests__/small-led-board.test.tsx`: page editor renders a 1 × 8 LED preview, the character counter shows 8, the page-list filter includes a 1 × 8 page for a 1 × 8 board). Fix what breaks.
- [ ] **Step 5: Run** the full Python non-integration suite and full web suite → PASS.
- [ ] **Step 6: Commit** — `fix(led): one-row LED boards lay out, transition and preview`.

---

## Track B — Plugin (`~/workspace/fiestaboard-output--ulanzi-tc001`)

Tests run inside `fb-tc001-test` with both repos mounted:
`docker run --rm -v ~/workspace/FiestaBoard-worktrees/tc001:/core -v "$PWD":/plugin -w /plugin fb-tc001-test ./run_tests.sh /core`

### Task 4: Scaffold the repo, manifest and device model

**Files:**

- Create (copied from TC002, then adapted): `__init__.py`, `manifest.json`, `output/device-models.json`, `LICENSE`, `README.md`, `CHANGELOG.md`, `package.json`, `.coveragerc`, `.gitignore`, `run_tests.sh`, `.github/workflows/ci.yml`, `tests/{__init__,conftest,mock_awtrix,test_manifest,test_conformance,test_core_driver}.py`, `tools/try_device.py`
- Do not copy `docs/*.jpg|png` (TC002 photos).

**Interfaces:**

- Produces: manifest id `ulanzi_tc001`; settings identical to TC002's (host, app_name, show_on_change, duration_s, tile_gap, block_padding, fade_style, username, password) **plus** `font`: `{"type": "string", "title": "Text size", "enum": ["3x5", "5x7"], "enumNames": ["Small — 8 characters", "Large — 5 characters"], "default": "3x5"}` — match the Pixoo's key: read `FONT_CONFIG_KEY` in `src/outputs/board_profile.py` and the Divoom repo's manifest (`gh api repos/Fiestaboard/fiestaboard-output--divoom-pixoo/contents/manifest.json`) and use the same key and shape.
- Device model `ulanzi_tc001`: label `Ulanzi TC001 (AWTRIX NG)`, `led_matrix`, family `awtrix_ng`, `pixels` 32 × 8, rgb 24, charset `led_3x5`, font `3x5`, `layoutOptions` = TC002's tileGap/blockPadding + `font: {"allowed": ["3x5", "5x7"], "default": "3x5"}`, animation stream `maxFps` 5 with notes/sources rewritten for the TC001 (no layout; one bitmap draw; 8192-byte JSON limit; RAM-only pushed apps), appearance as TC002.
- Python class renamed `AwtrixNGTC001`; module constants `PANEL_WIDTH = 32`, `PANEL_HEIGHT = 8`.
- `display.models` `["TC001"]`; keywords add `TC001`. `fiestaboard_version` `>=10.2.0`.

- [ ] **Step 1:** `git init` the directory; copy files; rename ids/names/strings (`grep -rni "tc002\|52\|17\|16" .` and review every hit).
- [ ] **Step 2: Tests first** — `tests/test_manifest.py` asserts: id/name/version above; `font` setting enum and default; device model geometry 32 × 8; `layoutOptions.font.allowed == ["3x5", "5x7"]`; core's `resolve_content_grid` on the model is `(1, 8)`, and `(1, 5)` with the 5x7 face. Run → FAIL until the manifest/model are right; fix; PASS.
- [ ] **Step 3: LICENSE** — MIT, two lines: `Copyright (c) 2026 Oliver Rummeyer` and `Copyright (c) 2026 FiestaBoard contributors`.
- [ ] **Step 4: CI** — `core_ref` default `feat/small-led-boards` with a comment `# Switch to main once FiestaBoard >=10.2.0 is released.`; also set the checkout `ref` default to match.
- [ ] **Step 5: Commit** — `feat: scaffold the Ulanzi TC001 output plugin from the TC002 plugin`.

### Task 5: Render a 32 × 8 frame in either face

**Files:** Modify `__init__.py` (render path); Test `tests/test_render.py` (rewrite).

**Interfaces:** Consumes Task 4. Produces `AwtrixNGTC001.render(frame) -> bytes` of exactly `32 * 8 * 3`; no `squeeze`/`GAP_ROW` (delete them and their docstring sections).

- [ ] **Step 1: Tests** — `test_a_frame_is_32x8_rgb888` (len 768); `test_8_characters_fit_at_3x5` (8 letters → all 8 drawn, glyph rows y 1–5); `test_5_characters_fit_at_5x7` (board config `font: "5x7"` → 5 drawn, y 0–6); `test_colour_tiles_draw_in_board_colours` (a `{63}` cell's pixels are the red the TC002 test uses); `test_a_canvas_layer_draws_over_the_text` (port the TC002 layer test to 32 × 8).
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement `render` as `rasterize(self.layout(frame)).pixels` (the frame is already 32 × 8); remove the squeeze and two-row centring. **Step 4:** PASS. **Step 5:** Commit `feat: render the TC001's 32x8 panel`.

### Task 6: Push frames as a plain bitmap app

**Files:** Modify `__init__.py` (`_payload`, module docstring), `tests/mock_awtrix.py`; Test `tests/test_writes.py`, `tests/test_device.py`.

**Interfaces:** Produces `_payload(pixels) -> {"draw": [["bitmap", 0, 0, 32, 8, <base64>]], ["durationMs": n]}` — no `layout` key. Before writing it, read AWTRIX NG's `docs/reference/payload.md` (draw commands) and `docs/api/openapi.yaml` (`PUT /api/v1/apps/pushed/{name}` body) from `https://github.com/Blueforcer/awtrix-ng` and match the exact field names; note in the module docstring which doc section it follows.

- [ ] **Step 1: Mock** — `mock_awtrix.py` answers `GET /api/v1/device` with `boardType: "awtrixng"` and a 32-wide panel field (name per the openapi schema), rejects a JSON body over 8192 bytes with 413, and rejects a pushed app carrying `layout` with 400 (an ESP32 has none).
- [ ] **Step 2: Tests** — `test_a_frame_is_one_bitmap_draw_without_a_layout`; `test_a_frame_body_fits_the_8192_byte_json_limit` (serialized size of a busy full-colour frame < 8192); port every TC002 write/stream/show-on-change/restart/fade/password test to the new payload and 768-byte frames.
- [ ] **Step 3:** Run → FAIL. **Step 4:** implement. **Step 5:** PASS with ≥ 80 % coverage. **Step 6:** Commit `feat: push each frame as one 32x8 bitmap`.

### Task 7: Tell a TC001 apart; discovery, tools, docs

**Files:** Modify `__init__.py` (`check_connection`, `_device`, `sweep`/discovery filter), `tools/try_device.py`, `README.md`, `CHANGELOG.md`; Test `tests/test_device.py`, `tests/test_discovery.py`, `tests/test_try_device.py`, `tests/test_conformance.py`.

**Interfaces:** Produces constants `ESP32 = "awtrixng"`, `TC002 = "tc002"`.

- [ ] **Step 1: Tests**
  - `test_a_tc001_connects` — boardType `awtrixng`, 32-wide → success, message `Connected to the TC001 at <host> (AWTRIX NG <version>).`
  - `test_a_tc002_is_refused_and_pointed_at_its_plugin` — boardType `tc002` → failure `bad_response`, message `<host> is a Ulanzi TC002, not a TC001.`, troubleshooting includes `Use the Ulanzi TC002 (AWTRIX NG) display instead.`
  - `test_a_wider_esp32_build_is_refused` — `awtrixng` with a 64-wide panel → failure, message `<host> is an AWTRIX NG clock 64 pixels wide; this display draws on the TC001's 32 x 8.`
  - Discovery lists only 32-wide `awtrixng` devices; `try_device.py` prints 32 × 8 frames.
  - `test_conformance.py` runs core's `OutputConformanceSuite` (as TC002 does) → no violations.
- [ ] **Step 2:** FAIL → implement → PASS (coverage ≥ 80 %).
- [ ] **Step 3: README** — rewrite for the TC001: requirements (flash AWTRIX NG via its web installer), quick start, the Text size setting (1 row of 8 / 1 row of 5) with a short "pages for the clock" section, how it behaves, settings table, Find my clock, Test connection, removing a board, a **Verify on your clock** table (full 32 × 8 bitmap draws unscaled; what `/api/v1/device` reports; sustained fps; `enlargeApps` has no effect), development, license + credit line: `Adapted from Oliver Rummeyer's [Ulanzi TC002 plugin](https://github.com/rummeyer/fiestaboard-output--ulanzi-tc002) (MIT).` No photos yet (none exist).
- [ ] **Step 4:** Commit `feat: recognise a TC001, find it, and document it`.

### Task 8: Marketplace listing (after the core release) — coordinator only

**Files:** core `plugin-registry.json`, `plugin-previews.json`, `README.md` LED matrix line.

- [ ] Gated on: core PR merged and released as ≥ 10.2.0; the owner's on-device check passing; the repo pushed to the org. Add an entry mirroring `ulanzi_tc002`'s with the TC001 id, name, description ("Show your FiestaBoard pages on a Ulanzi TC001 running AWTRIX NG … 1 row of 8 in the 3x5 font, or 5 in 5x7 …"), repository URL, and a preview teaser `"ULANZI TC001"`. Validate with `python scripts/validate_plugins.py --verbose` in the container. Separate PR to `main`.
