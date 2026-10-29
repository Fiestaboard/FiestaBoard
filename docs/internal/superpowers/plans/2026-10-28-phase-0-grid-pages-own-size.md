# Phase 0: Grid pages at their own text size on LED boards — Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An LED board shows every grid page whose grid it can produce at any text size its model allows. For example, a Pixoo 64 shows both 10×16 pages (3x5) and 8×10 pages (5x7). A page that needs a size other than the board's current one is drawn at that size and sent as one opaque full-frame pixel layer. The cells under it carry the page text, projected to the board's current grid. Pages a board can't produce at any size are flagged, never hidden: greyed, with a reason, in the page picker, the schedule form and the Pages list. A size change that leaves pages behind is listed in board settings. The board's Text size becomes the size new pages start at. Split-flap and FiestaPanel fit is unchanged. No output plugin changes.

**Architecture:** There is one fit rule in Python: `src/pages/fit.py` `page_fit_for_board`, built on `board_profile.producible_grids`. `pages_compatible_with_board` delegates to it, so every existing visibility and schedulability caller picks up the new rule without a signature change. Rendering takes an optional `face`:
- `PageService.render_page(..., face=)` renders the template, plugin context and canvases on that face's grid, using a face-specific `DisplayProfile` (`display_for_face`).
- `DisplayResult.face` records the face, and `content_key()` includes it.

At send time, `src/led/page_frame.py` turns a face result into one full-frame `CanvasLayer` (`send_layers`). The text is projected at the board's own grid, so the frame cache, `matches_frame` and LED transitions always compare same-shaped cells. The driver falls back to `fade` when a full frame is involved and a per-cell transition (flip, cascade) was asked for. The engine maps `plugin:` strategies to `fade` for face pages.

Web gets `producible_grids` on each board and mirrors the rule in `pageFitForBoard`, exactly as `pagesCompatibleWithBoard` mirrors `size_key` today. Previews of face pages are drawn client-side with FiestaUI's `modelWithLedFont(model, face)` over server cells at the page's own grid. That avoids sending a 64×64 RGBA frame per thumbnail.

**Tech Stack:** Python 3 / FastAPI / pydantic / pytest. React Router v7 + TanStack Query + vitest + msw. `@fiestaboard/ui` (`modelWithLedFont`).

**Spec:** docs/internal/superpowers/specs/2026-10-28-flexible-pages-design.md

## Global Constraints

- **Tests first.** Write each test, run it, and check that it fails for the stated reason (an assertion, or `ImportError`/`AttributeError` on the new name), not because of a typo or an unmocked request. One behaviour per test, named for the behaviour. Never weaken an assertion; if an existing test encoded the old contract, say so in the commit body.
- **Python test command.** Expand it literally each time, because shell state doesn't persist:
  `PYTHON_DOTENV_DISABLED=1 FIESTABOARD_OUTPUT_SEED_DIR=/private/tmp/claude-501/-Users-jeffre-workspace/2045ff4c-a837-434a-852f-ddb6d9ccdb9e/scratchpad/seed /private/tmp/claude-501/-Users-jeffre-workspace/2045ff4c-a837-434a-852f-ddb6d9ccdb9e/scratchpad/venv/bin/python3 -m pytest <paths> -q`
  Below this is written as `PYTEST <paths>`. Run from `/Users/jeffre/workspace/FiestaBoard/.claude/worktrees/flexible-pages-design`.
- **Web test command:** `(cd /Users/jeffre/workspace/FiestaBoard/.claude/worktrees/flexible-pages-design/web && npx vitest run <paths>)`. `node_modules` is symlinked from the main checkout. Never `npm install`.
- **Commits:** local only, no push. Every message ends with exactly `Co-Authored-By: Claude <noreply@anthropic.com>` (the repo CLAUDE.md rule).
- **Interface seam (fixed; Phase 1 is planned against these exact names):**
  - `src/outputs/board_profile.py`: `producible_grids(model: Mapping, config: Mapping | None) -> dict[str, tuple[int, int]]`
  - `src/pages/fit.py`: `@dataclass(frozen=True) class PageFit: fits: bool; face: str | None; reason: str | None` and `page_fit_for_board(page, board) -> PageFit`
  - `src/led/page_frame.py`: `full_frame_layer(frame: LedFrame) -> CanvasLayer` and `render_grid_page_frame(formatted: str, rows: int, cols: int, face: str, display: DisplayProfile, layers: Sequence[CanvasLayer] = ()) -> LedFrame`
  - `src/devices.py:886` `pages_compatible_with_board(page, board) -> bool` keeps its signature.
- **Unchanged behaviour:**
  - Split-flap, Vestaboard, note-array and FiestaPanel (both render styles) keep the exact `size_key` rule.
  - The family rule stays: only `panel` pages can match another face's grid, so a flagship page never fits an LED board even at 6×22.
  - The 3×10 LED floor applies: below-floor face grids are omitted.
  - An output that declares its own `character_set` has a fixed face, so it gets exact fit only.
- **No output-plugin changes.** The full frame rides `RichCells.layers` (`src/outputs/cells.py:81`), which LED plugins already paint last.
- **Render short-circuit and dedupe:** `_render_fingerprint` (`src/main.py:1794`) and `DisplayResult.content_key()` (`src/displays/service.py:46`) must change with the chosen face.
- **Reason copy** is plain and user-facing: `"Made for a {rows}×{cols} board"` (U+00D7).

## Review Focus

These are the five likely real-world inputs or failure modes that no task's main tests cover yet. Each now has a test in the owning task, marked **[RF]**.

1. **A legacy Pixoo saved before the text-size choice existed.** It has no `output_config.font` and a stored grid of 10×16. `board_font` resolves the face from the stored grid. An 8×10 page must still fit at face `5x7`, and a 10×16 page must use today's path. Test in Task 2.
2. **A Pixoo whose output plugin has been uninstalled.** `board_device_model` returns `None`. The fit must fall back to the exact rule without raising, both in the engine tick and in `find_incompatible_references`. Test in Task 2.
3. **A schedule entry pointing at a collection that mixes 10×16 and 8×10 pages, on an 8×10 Pixoo.** `check_ref_board_compatibility` must give no error and no "will be skipped" warnings. Today it warns for the 10×16 member. Test in Task 4.
4. **Leaving a face page for a native page while the board's transition is `flip`.** The before frame carries the full frame and the after frame doesn't. The flip's half-way layer swap would otherwise cut. The driver must fade. Test in Task 9.
5. **A face page whose own `transition_strategy` is `"plugin:typewriter"`.** The engine must send `"fade"`, because the transition plugin steps integer grids and would show the cropped projection. Test in Task 10.

### File Structure

| Path | Create/Modify | Responsibility |
|---|---|---|
| `src/outputs/board_profile.py` | Modify (after `_face_grid`, ~L201-207; `board_font` L210-253) | `producible_grids`, `board_producible_grids` |
| `src/pages/fit.py` | Create | `PageFit`, `page_fit_for_board`, `fit_reason` |
| `src/devices.py` | Modify L886-893 | `pages_compatible_with_board` delegates to the fit rule |
| `src/pages/service.py` | Modify L582-636 `render_page`, L638-664 `_apply_canvases`, L827-886 `preview_page`, L888-986 `preview_pages_batch`, L1074-1137 `check_ref_board_compatibility` | Rendering at a face; refusal copy |
| `src/displays/service.py` | Modify L30-60 | `DisplayResult.face`; `content_key` includes the face |
| `src/outputs/display_profile.py` | Modify (new function after `_profile`, ~L322) | `display_for_face` |
| `src/led/page_frame.py` | Create | `full_frame_layer`, `render_grid_page_frame`, `is_full_frame_layer`, `carries_full_frame`, `send_layers` |
| `src/outputs/transitions.py` | Modify (after `driver_runs_strategy`, ~L122) | `strategy_for_full_frame` |
| `src/outputs/plugin_driver.py` | Modify L567-612 `_render_transition` | Per-cell transition falls back to fade around full frames |
| `src/main.py` | Modify L129-153, L1766, L1794-1931, L2360-2470, L2525-2560, L2923-3035 | Engine fit gate, face render, fingerprint, projection, strategy |
| `src/pages/board_render.py` | Create | `render_page_for_board` (shared by route sends) |
| `src/pages/routes.py` | Modify L444-505 batch, L569-700 send | Faces in previews and sends |
| `src/pages/models.py` | Modify L510-528 | `PagePreviewBatchSuccess.face` |
| `src/settings/routes.py` | Modify L617-760 `set_active_page` send, L1163-1201 `_follow_resized_boards` | Face send; no retarget when the old grid is still producible; `left_behind_pages` |
| `src/settings/models.py` | Modify L378-417 | `LeftBehindPage`; `left_behind_pages` on `BoardSettingsUpdateResponse` |
| `src/settings/service.py` | Modify L345-385 `_mask_board` | `producible_grids` on board responses |
| `src/pages/retarget.py` | Modify (append) | `pages_left_behind` |
| `src/v1/routes_boards.py` | Modify L341-353 | `page_id` message send at a face |
| `src/templates/routes.py` | Modify L188-330 render, L378-530 live | Editor render and live send at a face |
| `src/ops/executors.py` L2253, `src/mcp_displays.py` L141 | Modify | Pass `left_behind_pages` through |
| `web/src/lib/api/boards.ts` (L330-500), `web/src/lib/api/pages.ts` (L207) | Modify | `producible_grids`, `LeftBehindPage`, preview `face` types |
| `web/src/lib/board-dimensions.ts` (L250-262) | Modify | `pageFitForBoard`; `pagesCompatibleWithBoard` delegates |
| `web/src/lib/device-preview.ts` | Modify | `pagePreviewTarget` (face model + layout) |
| `web/src/components/page-grid-selector.tsx` (L640-700, `PageButton` ~L250-330) | Modify | Flag misfits; previews drawn at the face |
| `web/src/components/schedule-entry-form.tsx` (L230-260, L449-470), `web/src/components/settings/silence-schedule.tsx` (L130-140) | Modify | Disabled options with reason |
| `web/app/routes/pages._index.tsx` (L144-150, L248) | Modify | Pages list shows misfits greyed but editable |
| `web/src/components/page-builder.tsx` (L905-936) | Modify | Editor previews at the page's face |
| `web/src/components/settings/display-settings.tsx` (L153-170, `BoardEditor` L364-740), `web/src/components/settings/output-boards.tsx` (L158-175), new `web/src/components/settings/left-behind-pages.tsx` | Modify/Create | "Pages left behind" list, Text size copy, fade note |
| `web/messages/en.json` | Modify | New strings |

**Call-site classification.** These are the callers of `geometry_of`, `size_key` and `pages_compatible_with_board` that decide visibility, schedulability or render shape.

| Module:line | Decides | Phase 0 change |
|---|---|---|
| `src/main.py:2464` send gate; `:2991` silence-page gate | Schedulability at send time | **Change** (Task 10): use `page_fit_for_board`; render at `fit.face`; log `fit.reason` |
| `src/main.py:1860, :1891` fingerprint size key and context | Short-circuit | **Change** (Task 8): face display key, and `face` in payload and memo |
| `src/main.py:2540, :3018` `_project` dims | Render shape | **Change** (Task 10): board dims plus `send_layers` when `fit.face` |
| `src/main.py:156, :2797` | Board's own size (logging, silence indicator) | No change |
| `src/pages/service.py:1110, :1127` `check_ref_board_compatibility` | Schedulability (API writes) | Auto via delegate; **copy change** (Task 4) |
| `src/pages/service.py:1198, :1277` `find_incompatible_*` | Warn-only reference scans | Auto via delegate (Task 3) |
| `src/pages/service.py:360, :369` delete replacement | Which page replaces the active one | Auto via delegate (the `:369` call passes a Page as "board", which `page_fit_for_board` treats with the exact rule) |
| `src/pages/service.py:517, :611, :621, :669, :679, :955` context keys | Plugin context per size | No change (a face page passes a face `display`, whose key separates the cache) |
| `src/pages/service.py:386` replacement geometry | New page size | No change |
| `src/pages/routes.py:487` batch preview | Preview shape | **Change** (Task 11) |
| `src/pages/routes.py:638, :690` page send | Render shape | **Change** (Task 11, via `render_page_for_board`) |
| `src/pages/routes.py:265-266` size-change detection on update | Reference scan trigger | No change |
| `src/settings/routes.py:746` immediate active-page send | Render shape | **Change** (Task 11) |
| `src/settings/routes.py:1174` `_resized_boards` | Board-vs-board | No change |
| `src/settings/routes.py:1195` retarget | Page moves on resize | **Change** (Task 12): skip when the old grid is still producible; report left-behind pages |
| `src/pages/retarget.py:35-94` | Retarget mechanics | No change, plus a new `pages_left_behind` (Task 12) |
| `src/panels/reconcile.py:103, :124`; `src/panels/routes.py:265` | FiestaPanel re-fit | No change (exact rule; the delegate never widens FiestaPanel) |
| `src/schedules/service.py:173`; `src/schedules/routes.py:139`; `src/mcp_server.py:1596`; `src/settings/routes.py:394, :671` | Schedulability via `check_ref_board_compatibility` | Auto (Task 3) and copy (Task 4) |
| `src/ops/executors.py:561`; `:2253`; `src/mcp_displays.py:141` | Reference scan / pass-through | Auto, plus `left_behind_pages` pass-through (Task 12) |
| `src/v1/routes_boards.py:345` message `page_id` | Render shape | **Change** (Task 11) |
| `src/v1/routes_boards.py:275, :319, :612` | Text, plugin and template sized to the board | No change |
| `src/v1/routes_meta.py:123`; `src/board_guards.py:115`; `src/displays/routes.py:301`; `src/board_api/routes.py:110, :522`; `src/outputs/display_profile.py:392` | The board's own grid | No change |
| `src/ai/prompt_builder.py:493, :511`; `src/ai/page_routes.py:732` | New-page authoring geometry = the target board's current grid | No change: this already makes the board's Text size the default for new pages |
| `src/templates/routes.py:328, :502` | Editor render and live send shape | **Change** (Task 13) |
| `src/mcp_server.py:268, :415, :1569, :1823`; `src/board_html_renderer.py:455`; `src/main.py:3147` held send | Explicit-geometry or text-only previews | No change in Phase 0 (they render text at the page's own grid; canvas previews at a face for Fiestabot come in Phase 5) |

---

### Task 1: `producible_grids` and `board_producible_grids`

**Files:**
- Modify: `src/outputs/board_profile.py`. Add both functions after `_face_grid` (L201-207). Reuse `offers_font_choice` (L192-199) and `layout_policy_for_model`.
- Test: `tests/test_producible_grids.py` (new)

**Interfaces:**
- Consumes: `layout_policy_for_model(model)["font"]["allowed"]` (`src/led/matrix.py:913`), `model_with_led_font` (`:1029`), `model_cell_grid` / `check_floor` / `BelowFloorError` (`src/outputs/geometry.py`), `charset_uses_cells` (`src/outputs/cells.py:152`), `board_character_set`, `board_device_model`, `output_registry`, `resolve_output_id`.
- Produces:
  - `producible_grids(model: Mapping, config: Mapping | None) -> dict[str, tuple[int, int]]`
  - `board_producible_grids(board: Mapping[str, Any]) -> dict[str, tuple[int, int]] | None`

- [ ] **Step 1: Write the failing tests.**
```python
from src.fiestaui import builtin_device_models
from src.outputs.board_profile import board_producible_grids, producible_grids
from tests.test_led_text_size import _board, declared_set_output, pixoo_output  # noqa: F401
MODELS = builtin_device_models()

def test_a_pixoo_produces_one_grid_per_text_size():
    assert producible_grids(MODELS["divoom_pixoo64"], None) == {"5x7": (8, 10), "3x5": (10, 16)}

def test_a_model_without_a_font_choice_produces_only_its_own_face():
    assert producible_grids(MODELS["hub75_64x32"], None) == {"5x7": (4, 10)}

def test_a_below_floor_grid_is_omitted():
    assert producible_grids(MODELS["ulanzi_tc001_awtrix"], None) == {}   # 1 x 8 at 3x5

def test_a_split_flap_model_produces_nothing():
    assert producible_grids(MODELS["vestaboard_flagship"], None) == {}

def test_a_pixoo_board_reports_both_grids(pixoo_output):
    assert board_producible_grids(_board()) == {"5x7": (8, 10), "3x5": (10, 16)}

def test_an_output_with_its_own_character_set_has_a_fixed_face(declared_set_output):
    grids = board_producible_grids(_board())
    assert grids is not None and len(grids) == 1

def test_a_vestaboard_has_no_producible_grids():
    assert board_producible_grids({"id": "b", "device_type": "flagship"}) is None
```
- [ ] **Step 2: Run.** `PYTEST tests/test_producible_grids.py`. Expected: `ImportError: cannot import name 'producible_grids'`.
- [ ] **Step 3: Implement.**
  - `producible_grids(model, config)`: return `{}` unless `offers_font_choice(model)`. For each face in `layout_policy_for_model(model)["font"]["allowed"]`, take `grid = model_cell_grid(model_with_led_font(model, face))` and keep it if `check_floor(model, *grid)` passes. Swallow `GeometryError`/`KeyError`/`ValueError` per face. `config` is accepted for the seam; Phase 0 reads nothing from it. Say so in the docstring.
  - `board_producible_grids(board)`:
    - `None` for `VESTABOARD`/`FIESTAPANEL`, an output that isn't installed, an output whose plugin class has `markup_follows_charset is False`, or a board whose `board_character_set` fails `charset_uses_cells` (the output can't receive layers).
    - An output with a declared `character_set` gets `{own_face: grid}` from `board_device_model(board)`.
    - Otherwise `producible_grids(base_model, board.get("output_config"))`, where `base_model` is `manifest.model(index)` exactly as `board_device_model` picks it.
- [ ] **Step 4: Run.** Same command. Expected: 7 passed.
- [ ] **Step 5: Commit.** `feat(outputs): grids an LED board can produce at each text size`

### Task 2: `PageFit` and `page_fit_for_board`

**Files:**
- Create: `src/pages/fit.py`
- Test: `tests/test_page_fit.py` (new)

**Interfaces:**
- Consumes: `geometry_of`, `size_key`, `dimensions_of`, `BoardInstance` (`src/devices.py`); `board_producible_grids` (Task 1); `board_font`/`board_device_model` (to read the current face).
- Produces:
  - `@dataclass(frozen=True) class PageFit: fits: bool; face: str | None; reason: str | None`
  - `page_fit_for_board(page, board) -> PageFit`
  - `fit_reason(page) -> str` (`"Made for a {rows}×{cols} board"`)

- [ ] **Step 1: Write the failing tests** (use the `pixoo_output` fixture and the `_board` helper from `tests/test_led_text_size.py`; pages are `Page(name=..., type="template", device_type=..., grid_rows=..., grid_cols=..., template=["HI"])`).
```python
def test_a_page_at_the_boards_own_grid_takes_todays_path(pixoo_output):
    assert page_fit_for_board(_page("panel", 10, 16), _board(output_config={"font": "3x5"})) == PageFit(True, None, None)

def test_a_page_at_the_other_text_size_fits_at_that_face(pixoo_output):
    board = _board(grid_rows=8, grid_cols=10, output_config={"font": "5x7"})
    assert page_fit_for_board(_page("panel", 10, 16), board) == PageFit(True, "3x5", None)

def test_a_flagship_page_on_a_pixoo_is_flagged_with_a_reason(pixoo_output):
    assert page_fit_for_board(_page("flagship"), _board()) == PageFit(False, None, "Made for a 6×22 board")

def test_a_panel_page_on_a_flagship_is_flagged(pixoo_output):
    fit = page_fit_for_board(_page("panel", 10, 16), {"id": "v", "device_type": "flagship"})
    assert (fit.fits, fit.reason) == (False, "Made for a 10×16 board")

def test_a_note_page_never_fits_a_one_by_one_note_array():
    assert not page_fit_for_board(_page("note"), {"id": "a", "device_type": "note_array"}).fits

def test_a_fixed_face_output_keeps_exact_fit(declared_set_output):
    assert not page_fit_for_board(_page("panel", 8, 10), _board()).fits

def test_a_page_passed_as_the_board_uses_the_exact_rule():
    assert page_fit_for_board(_page("flagship"), _page("flagship")).fits

# [RF1]
def test_a_legacy_board_without_a_stored_face_fits_the_other_size(pixoo_output):
    board = _board(output_config={"host": "192.0.2.50"})   # 10x16, no font key
    assert page_fit_for_board(_page("panel", 8, 10), board) == PageFit(True, "5x7", None)

# [RF2]
def test_a_board_whose_output_is_not_installed_falls_back_to_exact_fit():
    board = _board(output="not_installed")
    assert page_fit_for_board(_page("panel", 8, 10), board) == PageFit(False, None, "Made for a 8×10 board")
```
- [ ] **Step 2: Run.** `PYTEST tests/test_page_fit.py`. Expected: `ModuleNotFoundError: src.pages.fit`.
- [ ] **Step 3: Implement** `page_fit_for_board(page, board)` in `src/pages/fit.py`:
  1. If `size_key(*geometry_of(page)) == size_key(*geometry_of(board))`, return `PageFit(True, None, None)`.
  2. Normalise `board`: a `Mapping` is used as is; a `BoardInstance` goes through `.to_dict()`; anything else gets the exact rule (a mismatch with `fit_reason(page)`).
  3. `grids = board_producible_grids(board)`, wrapped in `try/except Exception` → `None`.
  4. If `geometry_of(page).device_type == "panel"` and `grids`, find the face whose grid equals `dimensions_of(page)` and isn't the board's current face (`board_font(board, base model)`). If found, return `PageFit(True, face, None)`.
  5. Otherwise return `PageFit(False, None, fit_reason(page))`. `fit_reason` falls back to the flagship's 6×22 when `dimensions_of` raises, mirroring `size_key`.
- [ ] **Step 4: Run.** Expected: 9 passed.
- [ ] **Step 5: Commit.** `feat(pages): the fit rule for grid pages on LED boards`

### Task 3: `pages_compatible_with_board` delegates

**Files:**
- Modify: `src/devices.py:886-893`
- Test: `tests/test_devices.py` (add); update the contract tests in `tests/test_led_text_size.py` (Task 12 owns their new assertions)

**Interfaces:**
- Consumes: `page_fit_for_board` (lazy import inside the function, to avoid a cycle `src.devices` → `src.pages`).
- Produces: unchanged `pages_compatible_with_board(page, board) -> bool`.

- [ ] **Step 1: Write the failing tests.**
```python
def test_an_led_board_is_compatible_with_a_page_at_its_other_text_size(pixoo_output):
    assert pages_compatible_with_board(_page("panel", 10, 16), _board(grid_rows=8, grid_cols=10, output_config={"font": "5x7"}))

def test_find_incompatible_board_references_skips_a_page_the_board_draws_at_another_size(pixoo_output):
    # active page 10x16 on an 8x10 Pixoo -> no reference reported
    ...
    assert find_incompatible_board_references(board) == []
```
Keep the existing split-flap and note-array tests in `tests/test_devices.py`; they must stay green.
- [ ] **Step 2: Run.** `PYTEST tests/test_devices.py -k "other_text_size or another_size"`. Expected: `AssertionError` (False).
- [ ] **Step 3: Implement.** Keep the exact `size_key` short-circuit; on a mismatch, `from src.pages.fit import page_fit_for_board` and `return page_fit_for_board(page, board).fits`. Update the docstring: LED boards fit any producible grid.
- [ ] **Step 4: Run.** `PYTEST tests/test_devices.py tests/test_deletion_references.py tests/test_pages_custom_grid_display.py tests/test_panel_geometry.py tests/test_pixel_canvas_stale_snapshot.py`. Expected: all pass, except any test asserting cross-face incompatibility on a Pixoo. Record those for Task 12; don't weaken them here.
- [ ] **Step 5: Commit.** `feat(devices): pages fit an LED board at any text size it allows`

### Task 4: Schedule and active-page refusals say why

**Files:**
- Modify: `src/pages/service.py:1074-1137`
- Test: `tests/test_page_fit_refusals.py` (new)

**Interfaces:**
- Consumes: `page_fit_for_board`.
- Produces: `check_ref_board_compatibility` error copy `f"Page '{name}' can't show on board {label}: {fit.reason}."`. The collection warning reads `f"Page '{name}' in collection '{c}' can't show on board {label} ({fit.reason}) and will be skipped."`.

- [ ] **Step 1: Write the failing tests.**
```python
def test_a_flagship_page_on_a_pixoo_is_refused_with_the_reason(pixoo_output):
    assert check_ref_board_compatibility(flagship_id, "pixoo-1").error.endswith("Made for a 6×22 board.")

# [RF3]
def test_a_collection_mixing_both_pixoo_sizes_fits_without_warnings(pixoo_output):
    result = check_ref_board_compatibility(mixed_collection_id, "pixoo-1")   # 10x16 + 8x10 members, board at 8x10
    assert (result.error, result.warnings) == (None, [])
```
- [ ] **Step 2: Run.** `PYTEST tests/test_page_fit_refusals.py`. Expected: the first fails on copy ("sizes must match exactly"). The second passes only once Task 3 is in; if it already passes, record it as covered by Task 3 and keep it as a regression.
- [ ] **Step 3: Implement.** Compute `fit = page_fit_for_board(p, board)` once per page and use `fit.fits`/`fit.reason` in both branches.
- [ ] **Step 4: Run.** `PYTEST tests/test_page_fit_refusals.py tests/test_schedules_contract.py tests/test_settings_contract.py`. Fix only assertions on the old copy, and name them in the commit body.
- [ ] **Step 5: Commit.** `feat(pages): say why a page can't be scheduled on a board`

### Task 5: `display_for_face`

**Files:**
- Modify: `src/outputs/display_profile.py` (new function after `_profile`, ~L322)
- Test: `tests/test_display_for_face.py` (new)

**Interfaces:**
- Consumes: `led_charset_for_font` (`src/led/matrix.py:1016`), `resolve_character_set`, `dataclasses.replace`.
- Produces: `display_for_face(display: DisplayProfile, face: str, grid: tuple[int, int]) -> DisplayProfile`

- [ ] **Step 1: Write the failing tests.** Start from the 5x7 Pixoo profile built by `display_profile_for_board` with the `_board(..., font="5x7")` helper.
```python
def test_the_face_profile_names_the_face_its_set_and_the_pages_grid(pixoo_output):
    d = display_for_face(five_by_seven, "3x5", (10, 16))
    assert (d.font, d.charset, d.rows, d.cols, d.width, d.height) == ("3x5", "led_3x5", 10, 16, 64, 64)

def test_the_face_profile_offers_only_the_faces_icons(pixoo_output):
    assert "snow" in five_by_seven.icons and "snow" not in display_for_face(five_by_seven, "3x5", (10, 16)).icons

def test_the_face_profile_keys_caches_apart_from_the_board(pixoo_output):
    assert display_for_face(five_by_seven, "3x5", (10, 16)).key != five_by_seven.key
```
- [ ] **Step 2: Run.** `PYTEST tests/test_display_for_face.py`. Expected: `ImportError`.
- [ ] **Step 3: Implement.** Resolve `charset = resolve_character_set(led_charset_for_font(face))`. Return `replace(display, font=face, rows=grid[0], cols=grid[1], charset=..., chars=..., icons=(filtered by BOARD_ICONS), mixed_case=..., color_spans=..., block_spans=..., tiles=..., _charset_json=...)`. These are the same field derivations `_profile` uses; factor them into a private `_charset_fields(charset)` that both call. Width, height, colour, tile_gap, block_padding and monochrome are kept.
- [ ] **Step 4: Run.** Expected: 3 passed. Also run `PYTEST tests/test_led_text_size.py -k Profile`.
- [ ] **Step 5: Commit.** `feat(outputs): a display profile for drawing a page at another text size`

### Task 6: `src/led/page_frame.py`

**Files:**
- Create: `src/led/page_frame.py`
- Test: `tests/test_led_page_frame.py` (new)

**Interfaces:**
- Consumes: `LedMatrixSpec`, `LedLayoutOptions`, `layout_message`, `rasterize`, `LedFrame`, `led_charset_for_font` (`src/led/matrix.py`); `project_message` (`src/outputs/cells.py:215`); `BUILTIN_CHARACTER_SETS`; `CanvasLayer` (`src/canvas/layer.py:30`); `DisplayProfile`.
- Produces:
  - `full_frame_layer(frame: LedFrame) -> CanvasLayer`
  - `render_grid_page_frame(formatted: str, rows: int, cols: int, face: str, display: DisplayProfile, layers: Sequence[CanvasLayer] = ()) -> LedFrame`
  - `is_full_frame_layer(layer: object, width: int, height: int) -> bool`
  - `carries_full_frame(cells: object, model: Mapping | None) -> bool`
  - `send_layers(result: Any, rows: int, cols: int, display: DisplayProfile | None) -> list[CanvasLayer]`

- [ ] **Step 1: Write the failing tests.** Use the Pixoo 64 at 5x7 as `display`. The 3x5 grid's origin is (0, 2); the 5x7 grid's origin is (2, 0).
```python
def px(frame, x, y): i = (y * frame.width + x) * 3; return frame.pixels[i:i + 3]

def test_a_10x16_page_draws_in_the_3x5_face_on_a_5x7_board():
    frame = render_grid_page_frame("H", 10, 16, "3x5", PIXOO_5X7)
    assert (frame.width, frame.height) == (64, 64) and px(frame, 0, 2) != b"\0\0\0"

def test_a_grid_the_face_does_not_produce_is_refused():
    with pytest.raises(ValueError, match="10x16"):
        render_grid_page_frame("H", 8, 10, "3x5", PIXOO_5X7)

def test_the_pages_canvas_layers_paint_over_the_text():
    red = CanvasLayer(x=0, y=2, w=1, h=1, rgba=bytes([255, 0, 0, 255]))
    assert px(render_grid_page_frame("H", 10, 16, "3x5", PIXOO_5X7, [red]), 0, 2) == bytes([255, 0, 0])

def test_a_monochrome_board_lights_text_in_its_panel_colour():
    mono = replace(PIXOO_5X7, monochrome="#ff0000", color="mono")
    assert px(render_grid_page_frame("H", 10, 16, "3x5", mono), 0, 2) == bytes([255, 0, 0])

def test_the_full_frame_layer_covers_the_matrix_opaquely_black_included():
    layer = full_frame_layer(render_grid_page_frame("", 10, 16, "3x5", PIXOO_5X7))
    assert (layer.x, layer.y, layer.w, layer.h) == (0, 0, 64, 64)
    assert set(layer.rgba[3::4]) == {255} and layer.rgba[:3] == b"\0\0\0"

def test_a_canvas_layer_is_not_a_full_frame():
    assert not is_full_frame_layer(CanvasLayer(0, 0, 64, 64, bytes(64 * 64 * 4)), 64, 64)   # alpha 0

def test_send_layers_wraps_a_face_result_and_passes_others_through():
    face = SimpleNamespace(formatted="H", layers=[], face="3x5")
    plain = SimpleNamespace(formatted="H", layers=["L"], face=None)
    assert is_full_frame_layer(send_layers(face, 10, 16, PIXOO_5X7)[0], 64, 64)
    assert send_layers(plain, 8, 10, PIXOO_5X7) == ["L"]
```
- [ ] **Step 2: Run.** `PYTEST tests/test_led_page_frame.py`. Expected: `ModuleNotFoundError`.
- [ ] **Step 3: Implement.**
  - `render_grid_page_frame` follows exactly what an LED plugin does with core's cells:
    - `charset = BUILTIN_CHARACTER_SETS[led_charset_for_font(face)]`
    - `cells = project_message(formatted, rows, cols, charset).cells`, which applies the same charset fallbacks a plugin receives
    - `spec = LedMatrixSpec(display.width, display.height, face, tile_gap=display.tile_gap, block_padding=display.block_padding)`
    - `options = LedLayoutOptions(monochrome=display.monochrome, charset=charset, tile_gap=display.tile_gap, block_padding=display.block_padding)`
    - `layout = layout_message(cells, spec, options, layers=layers)`
    - raise `ValueError(f"{face} draws {layout.grid.rows}x{layout.grid.cols} on this display, not {rows}x{cols}")` when the grid differs
    - return `rasterize(layout)`
  - `full_frame_layer` interleaves alpha 255 into the RGB bytes.
  - `is_full_frame_layer` checks `x == y == 0`, the size matches, and every alpha byte is 255.
  - `carries_full_frame` reads `model["geometry"]` width and height when its kind is `pixels`, then checks any `frame_layers(cells)`.
  - `send_layers` returns the wrapped frame only when `getattr(result, "face", None)` is set and `display` supports pixels.
- [ ] **Step 4: Run.** Expected: 7 passed.
- [ ] **Step 5: Commit.** `feat(led): draw a grid page at its own text size as one full-frame layer`

### Task 7: Render a page at a face (`PageService`, `DisplayResult`)

**Files:**
- Modify: `src/displays/service.py:30-60`, `src/pages/service.py:582-664, 827-886, 888-986`
- Test: `tests/test_page_render_face.py` (new)

**Interfaces:**
- Consumes: `display_for_face` (Task 5), `dimensions_of`.
- Produces:
  - `DisplayResult.face: str | None = None`; `content_key()` appends `"\x00face:{face}"` when set (before the layers check, so a face page with no canvases still keys apart)
  - `PageService.render_page(page, context=None, contexts=None, *, extended_markup=..., display=None, face: str | None = None)`
  - `preview_page(..., face: str | None = None)`
  - `preview_pages_batch(..., faces: Mapping[str, str | None] | None = None)`

- [ ] **Step 1: Write the failing tests.** The page is 10×16 with a canvas at `{"row": 1, "col": 1, "rows": 1, "cols": 2}`; the display is the 5x7 Pixoo profile.
```python
def test_a_face_render_places_canvases_on_that_faces_grid(pixoo_output):
    r = service.render_page(page, display=PIXOO_5X7, face="3x5")
    assert r.face == "3x5" and [(l.x, l.y, l.w, l.h) for l in r.layers] == [(0, 2, 7, 5)]

def test_plugins_are_fetched_for_the_face_display(pixoo_output):
    contexts = {}
    service.render_page(page, contexts=contexts, display=PIXOO_5X7, face="3x5")
    assert any(k.endswith(display_for_face(PIXOO_5X7, "3x5", (10, 16)).key) for k in contexts)

def test_the_content_key_moves_with_the_face():
    a = DisplayResult("page", "HI", {}, True); b = DisplayResult("page", "HI", {}, True, face="3x5")
    assert a.content_key() != b.content_key() and a.content_key() == "HI"

def test_a_face_is_ignored_off_a_pixel_display():
    assert service.render_page(flagship_page, face="3x5").face is None

def test_the_batch_renders_each_page_at_its_own_face(pixoo_output):
    out = service.preview_pages_batch([p10x16.id, p8x10.id], display=PIXOO_5X7, faces={p10x16.id: "3x5"})
    assert (out[p10x16.id].face, out[p8x10.id].face) == ("3x5", None)
```
- [ ] **Step 2: Run.** `PYTEST tests/test_page_render_face.py`. Expected: `TypeError: unexpected keyword argument 'face'`.
- [ ] **Step 3: Implement.**
  - In `render_page`, when `face and draws_pixels(display)`, rebind `display = display_for_face(display, face, (dims.rows, dims.cols))` before any context work. `_apply_canvases` already uses `display.font`, so canvases land on the face grid. After rendering, set `result.face = face`.
  - `preview_page` forwards `face` (a face render is uncached, like any display render).
  - `preview_pages_batch` renders pages whose `faces.get(pid)` is set individually, with `render_page(..., display=display, face=face)`, outside the shared per-size context build.
- [ ] **Step 4: Run.** `PYTEST tests/test_page_render_face.py tests/canvas tests/test_led_text_size.py`. Expected: new tests pass; nothing else changes.
- [ ] **Step 5: Commit.** `feat(pages): render a grid page at a given LED text size`

### Task 8: Render fingerprint reflects the face

**Files:**
- Modify: `src/main.py:1766` (`_RENDER_FINGERPRINT_VERSION` 2 → 3), `src/main.py:1794-1931`
- Test: `tests/test_render_fingerprint_cost.py` (add)

**Interfaces:**
- Produces: `_render_fingerprint(page, active_page_id, page_service, contexts, *, override_active, display=None, face: str | None = None) -> str | None`

- [ ] **Step 1: Write the failing tests** using the existing `rig`.
```python
def test_the_face_moves_the_fingerprint_within_the_same_tick(rig):
    assert _fp(rig, face=None) != _fp(rig, face="3x5")

def test_the_same_face_fingerprints_equal(rig):
    assert _fp(rig, face="3x5") == _fp(rig, face="3x5")
```
Extend the local `_fingerprint` helper with `face=`.
- [ ] **Step 2: Run.** `PYTEST tests/test_render_fingerprint_cost.py -k face`. Expected: `TypeError` on `face`.
- [ ] **Step 3: Implement.** When `face` and `display` are set, use `display_for_face(display, face, dims)` for the `size` key and the `shared_context_for` call, so they match Task 7's render key. Add `face` to `memo_key` and to the JSON payload, and bump the version.
- [ ] **Step 4: Run.** `PYTEST tests/test_render_fingerprint_cost.py`. Expected: all pass.
- [ ] **Step 5: Commit.** `feat(engine): the render short-circuit sees the page's text size`

### Task 9: The driver fades around full frames

**Files:**
- Modify: `src/outputs/plugin_driver.py:567-612`; `src/outputs/transitions.py` (add after L122)
- Test: `tests/test_full_frame_transitions.py` (new)

**Interfaces:**
- Consumes: `carries_full_frame` (Task 6), `resolve_transition`.
- Produces:
  - `strategy_for_full_frame(strategy: str | None) -> str | None` returns `"fade"` for `"flip"`, `"cascade"` or any `plugin:` strategy, and returns anything else unchanged.
  - The driver's `_render_transition` swaps a resolved `flip`/`cascade` for `resolve_transition("fade")` when `before` or `after` carries a full frame. If the device can't run fade either (the result is still per-cell), it snaps with `spec "none"`.

- [ ] **Step 1: Write the failing tests.** Use the `Sign` plugin from `tests/canvas/test_output_layers.py`, subclassed to record `transition`, bound to `model_with_led_font(PIXOO, "5x7")` (64×64) with `LED_5X7`, `geometry=(8, 10)`.
```python
def test_a_flip_into_a_full_frame_runs_as_fade():
    _render(driver, "A"); _render(driver, "B", [full]); assert plugin.transitions[-1].id == "fade"

def test_a_flip_between_ordinary_frames_stays_a_flip():
    _render(driver, "A"); _render(driver, "B"); assert plugin.transitions[-1].id == "flip"

# [RF4]
def test_leaving_a_full_frame_for_a_native_page_runs_as_fade():
    _render(driver, "A", [full]); _render(driver, "B"); assert plugin.transitions[-1].id == "fade"

def test_strategy_for_full_frame_maps_per_cell_and_plugin_strategies():
    assert [strategy_for_full_frame(s) for s in ("flip", "cascade", "plugin:typewriter", "slide", None)] == ["fade", "fade", "fade", "slide", None]
```
Here `_render(...)` calls `driver.render(chars, cells=..., strategy="flip")`. Pick a device model that runs both flip and fade (the `SEQUENCE` fixture, resized to 64×64, or the Pixoo with an explicit choice). Confirm with `transitions_for_model` before you write the assertion.
- [ ] **Step 2: Run.** `PYTEST tests/test_full_frame_transitions.py`. Expected: `ImportError` (`strategy_for_full_frame`); the driver tests fail with `"flip" != "fade"`.
- [ ] **Step 3: Implement** as specified. The check runs after `transition = self.resolve_transition(strategy)` (L587).
- [ ] **Step 4: Run.** `PYTEST tests/test_full_frame_transitions.py tests/canvas/test_output_layers.py tests/test_led_transitions.py tests/test_output_plugin_api.py`.
- [ ] **Step 5: Commit.** `feat(outputs): fade instead of flipping cells around a full-frame page`

### Task 10: The engine sends face pages (active page and silence page)

**Files:**
- Modify: `src/main.py`
  - helpers near L129-153
  - the stored-page branch L2360-2405: compute `fit` before the fingerprint
  - the gate L2460-2477: use `fit`
  - the send L2525-2560: dims, layers, strategy
  - `_send_silence_page` L2985-3035
- Test: `tests/test_engine_page_face.py` (new). Follow the `tests/test_silence_board_layer.py` harness: real `check_and_send_for_board`, with stubbed settings, clock and page service, and a `BoardRuntime` whose client is an `OutputPluginDriver` over a recording `Sign` bound to the 5x7 Pixoo model.

**Interfaces:**
- Consumes: `page_fit_for_board`, `PageFit`, `send_layers`, `strategy_for_full_frame`, `dimensions_of`.
- Produces: no new public names. `_project(client, content, rows, cols, layers)` is unchanged; callers now pass board dims and `send_layers(...)` for face pages.

- [ ] **Step 1: Write the failing tests.**
```python
def test_a_10x16_page_reaches_an_8x10_pixoo_as_cells_plus_one_full_frame(engine):
    engine.tick(active=page_10x16)
    cells = engine.plugin.last_cells
    assert (len(cells), len(cells[0])) == (8, 10)
    assert len(cells.layers) == 1 and is_full_frame_layer(cells.layers[0], 64, 64)

def test_the_cells_under_the_frame_carry_the_page_text(engine):
    engine.tick(active=page_10x16_with("HELLO"))
    assert "".join(t.value or "" for t in engine.plugin.last_cells[0]).startswith("HELLO")

def test_a_page_at_the_boards_own_size_is_sent_as_cells_only(engine):
    engine.tick(active=page_8x10); assert engine.plugin.last_cells.layers == ()

def test_a_flagship_page_is_skipped_with_its_reason_logged(engine, caplog):
    assert engine.tick(active=flagship_page) is False and "Made for a 6×22 board" in caplog.text

def test_an_unchanged_face_page_is_not_rendered_twice(engine):
    engine.tick(active=page_10x16); engine.tick(active=page_10x16); assert engine.renders == 1

def test_a_silence_page_at_the_other_size_is_shown_not_replaced_by_the_indicator(engine):
    engine.tick(silence_page=page_10x16); assert len(engine.plugin.last_cells.layers) == 1

# [RF5]
def test_a_face_pages_own_transition_plugin_runs_as_fade(engine):
    engine.tick(active=page_10x16_with_strategy("plugin:typewriter"))
    assert engine.client_render_kwargs["strategy"] == "fade"
```
- [ ] **Step 2: Run.** `PYTEST tests/test_engine_page_face.py`. Expected: the first, second, fourth, fifth and RF5 tests fail on assertions (today's gate skips the page; size-key wording). The third passes as a regression guard.
- [ ] **Step 3: Implement.**
  1. Move `board_dims_source = board if board is not None else self._board_dict_for(board_id)` up to just after `page` is known, in both branches. Set `fit = page_fit_for_board(page, board_dims_source) if board_dims_source is not None else PageFit(True, None, None)`.
  2. Pass `face=fit.face` to `_render_fingerprint` and to `preview_page`.
  3. Replace the gate's `pages_compatible_with_board` with `not fit.fits`. Log `fit.reason` instead of the two size keys; keep the once-per-mismatch logic.
  4. At send, use `dims = dimensions_of(board_dims_source) if fit.face else dimensions_of(page)`, `layers = send_layers(result, *page_dims, display)` (where `display = _extended_kw(client).get("display")`), and `strategy = strategy_for_full_frame(strategy) if fit.face else strategy`.
  5. Apply the same three changes in `_send_silence_page`. There, `dims` stays the board's (`resolve_dimensions(device_type, ...)`).
- [ ] **Step 4: Run.** `PYTEST tests/test_engine_page_face.py tests/test_silence_board_layer.py tests/test_multi_board_driving.py tests/test_render_fingerprint_cost.py tests/canvas`.
- [ ] **Step 5: Commit.** `feat(engine): show grid pages on LED boards at their own text size`

### Task 11: Route sends and previews at a face

**Files:**
- Create: `src/pages/board_render.py`
- Modify:
  - `src/pages/routes.py` L444-505 (batch preview) and L569-700 (send)
  - `src/settings/routes.py` L617-760 (`set_active_page` immediate send)
  - `src/v1/routes_boards.py` L341-353
  - `src/pages/models.py` L510-528 (`face: str | None = None` on `PagePreviewBatchSuccess`)
- Test: `tests/test_routes_page_face.py` (new). Reuse the harness from `tests/canvas/test_page_send_layers.py` (`Sign`, `client`, `output_plugin`), with the board at 8×10 and font 5x7.

**Interfaces:**
- Produces: `render_page_for_board(page_service, page_id: str, board: Mapping | None, render_kw: Mapping, *, force_refresh: bool = True) -> tuple[DisplayResult | None, list[CanvasLayer], PageFit]`. The layers come from `send_layers`. Routes don't gate: when `not fit.fits` the face is `None`, which is today's crop path.

- [ ] **Step 1: Write the failing tests.**
```python
@pytest.mark.parametrize("endpoint", ["message", "active-page", "pages-send"])
def test_a_10x16_page_sent_to_an_8x10_board_arrives_as_one_full_frame(client, endpoint, output_plugin):
    ...
    assert len(plugin.calls[-1][-1].layers) == 1 and is_full_frame_layer(plugin.calls[-1][-1].layers[0], 64, 64)

def test_the_batch_preview_draws_a_face_page_at_its_own_grid(api):
    entry = client.post("/pages/preview/batch", json={"page_ids": [pid], "board_id": "pixoo-1"}).json()["previews"][pid]
    assert entry["face"] == "3x5" and (len(entry["cells"]), len(entry["cells"][0])) == (10, 16)
    assert [(l["x"], l["y"]) for l in entry["layers"]] == [(0, 2)]
```
- [ ] **Step 2: Run.** `PYTEST tests/test_routes_page_face.py`. Expected: `assert 0 == 1` (no layer) and `KeyError: 'face'`.
- [ ] **Step 3: Implement.**
  - The three send routes swap `preview_page` plus `layers=result.layers` for `render_page_for_board` and apply `strategy_for_full_frame` when `fit.face`.
  - The batch route builds `faces = {pid: page_fit_for_board(page, board).face}` for its board and passes `faces=`.
  - For face entries the batch route projects cells at the page's own dims and sets `"face"`. Layers are the canvas layers on the face grid, never the full frame, which keeps thumbnails light.
- [ ] **Step 4: Run.** `PYTEST tests/test_routes_page_face.py tests/canvas/test_page_send_layers.py tests/test_pages_contract.py tests/test_v1_contract.py tests/test_settings_contract.py`.
- [ ] **Step 5: Commit.** `feat(api): page sends and previews use the page's own text size`

### Task 12: Board settings: no retarget on a text-size change; list pages left behind; `producible_grids`

**Files:**
- Modify:
  - `src/settings/routes.py:1163-1201` (`_follow_resized_boards`)
  - `src/pages/retarget.py` (append `pages_left_behind`)
  - `src/settings/models.py:378-417` (`LeftBehindPage`, `left_behind_pages`)
  - `src/settings/service.py:345-385` (`_mask_board`)
  - `src/ops/executors.py:2253` and `src/mcp_displays.py:141` (pass-through)
- Test: `tests/test_led_text_size.py` (update the contract tests below) and `tests/test_left_behind_pages.py` (new)

**Interfaces:**
- Produces:
  - `pages_left_behind(resized: list[tuple[dict, dict]], moved_ids: set[str]) -> list[dict]` returning `{board_id, board_name, page_id, page_name, page_size, reason}`
  - `class LeftBehindPage(BaseModel)` with those fields
  - `BoardSettingsUpdateResponse.left_behind_pages: list[LeftBehindPage] | None = None`
  - `GET /settings/board` boards gain `producible_grids: {face: [rows, cols]}`, only when `board_producible_grids(board)` isn't `None`

- [ ] **Step 1: Write the failing tests.** Change the old-contract tests in `tests/test_led_text_size.py`; this is a deliberate contract change, so say so in the commit body:
```python
def test_a_text_size_switch_leaves_pages_at_their_own_size(self, pixoo_output, client):   # was ..._follow_the_board_both_ways
    board_id = _create(client, font="3x5"); page_id = _page(10, 16)
    body = _switch(client, board_id, "5x7")
    assert _page_grid(page_id) == ("panel", 10, 16) and body["retargeted_pages"] == []
    assert body["incompatible_references"] == [] and body["left_behind_pages"] == []

def test_a_page_at_the_old_size_stays_active_after_a_switch(self, pixoo_output, client):   # was ..._when_another_board_still_has_the_old_size
    ...; assert body["incompatible_references"] == []
```
Also update `test_a_plugin_sees_the_new_size_and_face_after_a_switch...` and `test_the_engine_path_renders_the_page_at_the_new_grid...`. The 10×16 page is no longer retargeted, so the plugin now sees `(10, 16, "led_3x5", "3x5")` after the switch. Assert that.

New tests:
```python
def test_a_note_array_resize_lists_the_pages_it_left_behind(client):
    body = resize_array(client, notes_wide=4)   # 2-wide -> 4-wide, page sized 3x30
    assert [(p["page_name"], p["reason"]) for p in body["left_behind_pages"]] == [("Transit", "Made for a 3×30 board")]

def test_a_pixoo_board_response_names_its_grids(pixoo_output, client):
    assert board_json(client, "pixoo-1")["producible_grids"] == {"5x7": [8, 10], "3x5": [10, 16]}

def test_a_flagship_board_response_has_no_grids(client):
    assert "producible_grids" not in board_json(client, "hall-1")
```
- [ ] **Step 2: Run.** `PYTEST tests/test_led_text_size.py tests/test_left_behind_pages.py`. Expected: the pages are retargeted (`("panel", 8, 10)`); `KeyError` on `left_behind_pages` and `producible_grids`.
- [ ] **Step 3: Implement.**
  - In `_follow_resized_boards`, skip `add_resize(resizes, old, new)` when `pages_compatible_with_board(old, new)`: the board can still produce its old grid, so its pages still fit.
  - Collect `moved_ids` and add `left_behind_pages = pages_left_behind(resized, moved_ids)`. A page is left behind when its `size_key` equals the old board's, it wasn't moved, and it doesn't fit the new board; the reason is its `fit_reason`.
  - Add `producible_grids` in `_mask_board`.
  - Pass the new field through the two MCP/ops responses.
- [ ] **Step 4: Run.** `PYTEST tests/test_led_text_size.py tests/test_left_behind_pages.py tests/test_settings_contract.py tests/test_output_board_settings_contract.py tests/test_panel_content_resize.py`.
- [ ] **Step 5: Commit.** `feat(settings): text size no longer moves pages; list pages a resize left behind`

### Task 13: Editor render and live send at a face

**Files:**
- Modify: `src/templates/routes.py` L188-330 (`render_template`, `_render_canvas_page`, `_render_geometry`) and L378-530 (`render_template_live`); the response model gains `face: str | None` (find `TemplateRenderLiveResponse`/the render response in `src/templates/models.py`)
- Test: `tests/test_template_render_face.py` (new)

**Interfaces:**
- Consumes: `page_fit_for_board(Geometry-as-dict of the request, target_board)`, `display_for_face`, `send_layers`.

- [ ] **Step 1: Write the failing tests.**
```python
def test_the_editor_renders_a_10x16_page_on_an_8x10_board_at_3x5(pixoo_output, client):
    r = client.post("/templates/render", json={"template": ["HI"], "board_id": bid, "device_type": "panel", "grid_rows": 10, "grid_cols": 16, "canvases": [CANVAS]}).json()
    assert r["face"] == "3x5" and (r["layers"][0]["x"], r["layers"][0]["y"]) == (0, 2)

def test_a_live_send_of_that_page_arrives_as_one_full_frame(pixoo_output, client, recording_driver):
    ...; assert is_full_frame_layer(recording_driver.last_cells.layers[0], 64, 64)
```
- [ ] **Step 2: Run.** `PYTEST tests/test_template_render_face.py`. Expected: `KeyError: 'face'`, and the layer sits at (2, 0).
- [ ] **Step 3: Implement.** When the request names a geometry and `fit.face` is set, render with `display_for_face(display, face, (rows, cols))`. The live send then projects at the board's dims with `send_layers` (`live_strategy` already drops `plugin:`).
- [ ] **Step 4: Run.** `PYTEST tests/test_template_render_face.py tests/test_templates_contract.py tests/test_led_text_size.py -k template`.
- [ ] **Step 5: Commit.** `feat(templates): the editor draws and sends a page at its own text size`

### Task 14 (web): `pageFitForBoard` mirror and types

**Files:**
- Modify: `web/src/lib/board-dimensions.ts:212-262`; `web/src/lib/api/boards.ts` (`BoardInstance.producible_grids?: Record<string, [number, number]> | null`; `LeftBehindPage`; `BoardSettingsUpdateResult.left_behind_pages?`); `web/src/lib/api/pages.ts:207` (`face?: string | null` on the preview entry)
- Test: `web/src/__tests__/board-dimensions-page-fit.test.ts` (new)

**Interfaces:**
- Produces:
  - `export interface PageFit { fits: boolean; face: string | null; rows: number; cols: number }` (`rows`/`cols` are the page's, for the reason copy)
  - `export function pageFitForBoard(page: SizedEntity, board: SizedEntity & { producible_grids?: Record<string, [number, number]> | null; led_layout?: { font?: string } | null }): PageFit`
  - `pagesCompatibleWithBoard` returns `pageFitForBoard(...).fits`

- [ ] **Step 1: Write the failing tests.**
```ts
const PIXOO = { device_type: "panel", grid_rows: 8, grid_cols: 10, producible_grids: { "5x7": [8, 10], "3x5": [10, 16] }, led_layout: { font: "5x7" } };
it("fits a 10x16 page on an 8x10 Pixoo at 3x5", () =>
  expect(pageFitForBoard({ device_type: "panel", grid_rows: 10, grid_cols: 16 }, PIXOO)).toEqual({ fits: true, face: "3x5", rows: 10, cols: 16 }));
it("takes today's path at the board's own grid", () =>
  expect(pageFitForBoard({ device_type: "panel", grid_rows: 8, grid_cols: 10 }, PIXOO).face).toBeNull());
it("flags a flagship page on a Pixoo", () =>
  expect(pageFitForBoard({ device_type: "flagship" }, PIXOO)).toMatchObject({ fits: false, rows: 6, cols: 22 }));
it("keeps the exact rule for a board with no producible grids", () =>
  expect(pagesCompatibleWithBoard({ device_type: "note" }, { device_type: "note_array" })).toBe(false));
```
- [ ] **Step 2: Run.** `(cd …/web && npx vitest run src/__tests__/board-dimensions-page-fit.test.ts)`. Expected: `pageFitForBoard is not a function`.
- [ ] **Step 3: Implement.** Same algorithm as Task 2. The current face is `board.led_layout?.font`.
- [ ] **Step 4: Run.** That test plus `src/__tests__/board-dimensions*.test.ts`.
- [ ] **Step 5: Commit.** `feat(web): mirror the LED text-size fit rule`

### Task 15 (web): Page picker and Pages list flag misfits

**Files:**
- Modify:
  - `web/src/components/page-grid-selector.tsx`: props ~L620-645; filtering L665-676; `previewTargets` L683-700; `PageButton` ~L250-330
  - `web/src/lib/device-preview.ts`: add `pagePreviewTarget`
  - `web/app/routes/pages._index.tsx`: L144-150, L248
  - `web/messages/en.json`: `pageFit.madeFor`, `pageFit.notOnThisDisplay`
- Test: `web/src/__tests__/page-grid-selector-fit.test.tsx` (new). Update `page-grid-selector.test.tsx` and `pages-index-current-display.test.tsx`, where they assert misfits are hidden (a contract change; name them in the commit).

**Interfaces:**
- Produces:
  - `PageGridSelectorProps.misfitsSelectable?: boolean` (default `false`)
  - `pagePreviewTarget(board, page): { model: DeviceModel | null; ledLayout: BoardLedLayout | null }`. It uses `modelWithLedFont(model, fit.face)` from `@fiestaboard/ui` and `{ ...board.led_layout, font: fit.face }` when `fit.face` is set.

- [ ] **Step 1: Write the failing tests.**
```tsx
it("shows a page the board can't produce, greyed, with its reason", async () => {
  render(<PageGridSelector filterByCurrentBoardSize onSelect={onSelect} />);   // currentBoard = PIXOO 8x10
  const card = await screen.findByRole("button", { name: /Flagship page/ });
  expect(card).toBeDisabled();
  expect(within(card).getByText("Made for a 6×22 board")).toBeInTheDocument();
});
it("lists misfits after the pages that fit", ...);   // order of names
it("lets the Pages list open a misfit for editing", async () => {
  render(<PageGridSelector compatibleBoard={PIXOO} misfitsSelectable onSelect={onSelect} />);
  await userEvent.click(await screen.findByRole("button", { name: /Flagship page/ }));
  expect(onSelect).toHaveBeenCalledWith("flag");
});
it("previews a 10x16 page on an 8x10 Pixoo in the 3x5 face", ...);   // DevicePreview receives model.font === "3x5"
```
- [ ] **Step 2: Run.** `npx vitest run src/__tests__/page-grid-selector-fit.test.tsx`. Expected: the misfit card is not found (it's filtered out today).
- [ ] **Step 3: Implement.**
  - Stop filtering by fit. Sort fits first, then mark each misfit `disabled={!misfitsSelectable}` with `aria-describedby` pointing at the reason line (`t("pageFit.madeFor", { rows, cols })`), styled `opacity-60`.
  - The `deviceTypeFilter` filter stays as is.
  - `previewTargets` uses `pagePreviewTarget`.
  - `pages._index.tsx` passes `misfitsSelectable`; `libraryCount` keeps counting the pages that fit.
- [ ] **Step 4: Run.** The new test plus `page-grid-selector*.test.tsx` and `pages-index-*.test.tsx`.
- [ ] **Step 5: Commit.** `feat(web): flag pages a display can't show instead of hiding them`

### Task 16 (web): Schedule form and silence picker flag misfits

**Files:**
- Modify: `web/src/components/schedule-entry-form.tsx` L230-260 and L449-470; `web/src/components/settings/silence-schedule.tsx` L130-140 and its `SelectItem` list
- Test: update `web/src/__tests__/schedule-entry-form-size-filter.test.tsx` (contract change: misfits are now shown disabled)

- [ ] **Step 1: Write the failing tests.**
```tsx
it("offers a page that doesn't fit as a disabled option with its reason", async () => {
  ...open the page select...
  const option = screen.getByRole("option", { name: /Note Page/ });
  expect(option).toHaveAttribute("aria-disabled", "true");
  expect(option).toHaveTextContent("Made for a 3×15 board");
});
it("offers a 10x16 page to an 8x10 Pixoo as selectable", ...);
it("warns with the reason when editing an entry whose page no longer fits", ...);
```
- [ ] **Step 2: Run.** `npx vitest run src/__tests__/schedule-entry-form-size-filter.test.tsx`. Expected: no "Note Page" option.
- [ ] **Step 3: Implement.** `visiblePages = pages`. Each `SelectItem` gets `disabled={!fit.fits && p.id !== pageId}` and a muted reason span. `sizeWarning` uses the reason copy. The silence picker gets the same treatment.
- [ ] **Step 4: Run.** `npx vitest run src/__tests__/schedule-entry-form-*.test.tsx src/__tests__/*silence*.test.tsx`.
- [ ] **Step 5: Commit.** `feat(web): schedule and silence pickers flag pages that don't fit`

### Task 17 (web): Editor previews at the page's face

**Files:**
- Modify: `web/src/components/page-builder.tsx:905-940` (`previewModel`, `pixelBoard`); `web/src/lib/device-preview.ts` (uses `pagePreviewTarget` from Task 15)
- Test: `web/src/__tests__/device-preview-face.test.ts` (new)

- [ ] **Step 1: Write the failing tests.**
```ts
it("draws a 10x16 page on an 8x10 Pixoo with the 3x5 model", () => {
  const { model, ledLayout } = pagePreviewTarget(PIXOO_8x10_BOARD, { device_type: "panel", grid_rows: 10, grid_cols: 16 });
  expect([model?.font, ledLayout?.font]).toEqual(["3x5", "3x5"]);
});
it("leaves the board's own model for a page at its grid", ...);
```
- [ ] **Step 2: Run.** Expected: `pagePreviewTarget is not a function`, unless Task 15 landed first; in that case write the page-builder assertion so it fails on the model font instead.
- [ ] **Step 3: Implement.** `previewModel` and `pixelBoard` read from `pagePreviewTarget(previewBoard, currentShape)`.
- [ ] **Step 4: Run.** The new test plus `src/__tests__/page-builder*.test.tsx`.
- [ ] **Step 5: Commit.** `feat(web): the editor previews a page at its own text size`

### Task 18 (web): Board settings: pages left behind, Text size copy, fade note

**Files:**
- Create: `web/src/components/settings/left-behind-pages.tsx`
- Modify:
  - `web/src/components/settings/display-settings.tsx`: `useDisplayBoards` L153-170 keeps a `leftBehind: Record<string, LeftBehindPage[]>` from the PUT response; `BoardEditor` L364-740 renders `<LeftBehindPages>` above the connection section
  - `web/src/components/settings/output-boards.tsx:158-175`: set `description` on the `font` schema property when `Object.keys(board.producible_grids ?? {}).length > 1`
  - `web/messages/en.json`
- Test: `web/src/__tests__/board-left-behind.test.tsx` (new); update `board-resize-toast.test.tsx` (the moved-pages toast stays)

- [ ] **Step 1: Write the failing tests.**
```tsx
it("lists pages a resize left behind, with each reason", async () => {
  respondWith({ retargeted_pages: [], incompatible_references: [], left_behind_pages: [{ board_id: "a", board_name: "Array", page_id: "p1", page_name: "Transit", page_size: "note_array:3x30", reason: "Made for a 3×30 board" }] });
  ...render BoardEditor for board "a", save...
  expect(await screen.findByRole("region", { name: "Pages this display no longer shows" })).toHaveTextContent("Transit — Made for a 3×30 board");
});
it("says Text size is the size new pages start at", ...);   // the font field description text
it("notes that pages at another text size use Fade", ...);   // shown when producible_grids has >1 entry
```
Copy:
- Text size description: "The size new pages start at. Pages made at the other size still show, at their own size."
- Fade note: "Pages at the other text size change with Fade. Flip, Cascade and transition plugins need the display's own text size."
- [ ] **Step 2: Run.** `npx vitest run src/__tests__/board-left-behind.test.tsx`. Expected: the region is not found.
- [ ] **Step 3: Implement** as described. The list carries links to `/pages/edit/{id}`. Use FiestaUI `Alert`, with no accent rails.
- [ ] **Step 4: Run.** The new test plus `board-resize-toast.test.tsx` and `display-settings*.test.tsx`.
- [ ] **Step 5: Commit.** `feat(web): board settings list pages a resize left behind`

### Task 19: Full verification

- [ ] `PYTEST tests -q -x -p no:cacheprovider`. Every failure must be either fixed or named in a commit as an intentional contract change. The expected ones are in `tests/test_led_text_size.py` and the web filter tests, already handled above.
- [ ] `(cd …/web && npx vitest run)`, then `npx tsc --noEmit` and `npx eslint src app`.
- [ ] Revert-proof the load-bearing tests: temporarily make `pages_compatible_with_board` exact again and confirm Tasks 3, 4 and 10 fail; drop the `face` from `content_key` and confirm Task 7's key test fails. Restore. Put the observed failures in the PR description.

---

## Self-review against the spec

**Coverage (spec §7 and phasing item 0):**
- "Fits if its grid is any grid the board can produce": Tasks 1-3.
- "Renders at the size that produces its grid": Tasks 5-7 and 10.
- "Delivery reuses the full-frame path; cells carry the page text projected to the board's current grid": Tasks 6, 10 and 11.
- "A page at the board's own size keeps today's path": `face is None` is asserted in Tasks 2, 10 and 14.
- "Text size becomes a default": new-page authoring already uses the board's current grid (`ai/prompt_builder`, page-builder `?board=`); Task 18 adds the copy; Task 12 stops a size switch rewriting pages.
- "Flagged, not hidden, with a reason" in the picker, schedule form and Pages list: Tasks 15 and 16, plus API refusals (Task 4).
- "Size changes that leave pages behind are listed in board settings": Tasks 12 and 18.
- "Split-flap and TV split-flap keep exact fit": Task 1 returns `None` for both, and Task 2's family-rule test guards it.
- Transitions fall back to fade, shown in board settings: Tasks 9, 10 and 18.
- Fingerprint and dedupe reflect the face: Tasks 7 and 8.

**Gaps, stated:**
- The page's own transition picker in the editor doesn't yet show the fade note; only board settings does. Add it in Phase 4, or add a line to Task 18 if review wants it now.
- Panel re-fits (`PATCH /panels`) keep their toast and don't feed the left-behind list; FiestaPanel is out of Phase 0's scope.
- Fiestabot previews (`mcp_server.py:415`) still draw canvases at the board's face for a face page; that is deferred to Phase 5.
- "Now showing" (`active-page-display.tsx`) draws read-back cells at the board grid. A face page shows its projected text there, not the frame. That is acceptable, because the cells are real text, but worth a reviewer's eye.
- Output plugins that receive rich cells but ignore `frame.layers` would show the projected, cropped text. The spec says this was verified for the Divoom plugin; others are assumed per the output_api 1 layer contract.

**Type consistency:**
- `producible_grids` and `board_producible_grids` return `tuple[int, int]` values; JSON sends `[rows, cols]` and TypeScript reads `[number, number]`.
- `PageFit(fits, face, reason)` in Python versus `{fits, face, rows, cols}` in the web: the reason is localised client-side from rows and cols. The server's `reason` string and `madeFor` copy must stay identical ("Made for a {rows}×{cols} board").
- `face` is the face id string everywhere: `DisplayResult.face`, `PagePreviewBatchSuccess.face`, the template render `face`.
- `render_grid_page_frame` takes the board's `DisplayProfile`, not the face display; only width, height, tile_gap, block_padding and monochrome are read from it, and the charset comes from the face.
- `send_layers` returns canvas layers unchanged for non-face results, so every existing caller's bytes are unchanged.

### Critical Files for Implementation
- /Users/jeffre/workspace/FiestaBoard/.claude/worktrees/flexible-pages-design/src/outputs/board_profile.py
- /Users/jeffre/workspace/FiestaBoard/.claude/worktrees/flexible-pages-design/src/pages/fit.py (new)
- /Users/jeffre/workspace/FiestaBoard/.claude/worktrees/flexible-pages-design/src/led/page_frame.py (new)
- /Users/jeffre/workspace/FiestaBoard/.claude/worktrees/flexible-pages-design/src/main.py
- /Users/jeffre/workspace/FiestaBoard/.claude/worktrees/flexible-pages-design/src/pages/service.py
- /Users/jeffre/workspace/FiestaBoard/.claude/worktrees/flexible-pages-design/web/src/lib/board-dimensions.ts
