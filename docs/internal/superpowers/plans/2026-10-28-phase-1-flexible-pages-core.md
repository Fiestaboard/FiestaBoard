# Phase 1: Flexible pages core and LED layout — Implementation Plan
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `flexible` page type (schema v7). It renders on every board. Pixel boards get a server-laid-out full-frame image, delivered through Phase 0's full-frame layer, with real cell text underneath. Split-flap boards get the same character-grid cell layout. Every compromise is reported as a path-carrying `layout_issues` entry.

**Architecture:** There is one new pure package, `src/layout/`. It contains the font registry (families over the vendored faces), the style resolver, expansion, measure/fit, the stack, the pixel emitter and the cell layout. `PageService.render_page` dispatches `type == "flexible"` to `layout_flexible_page()`, which returns a `FlexRender` (frame, cell lines, issues). The service turns it into a `DisplayResult` with:

- `formatted` set to the cell lines at the board's grid;
- `layers` set to `[full_frame_layer(frame)]`;
- `layout_issues`.

Glyphs are drawn with the existing `src/led/matrix.draw_glyph`/`paint_ops`, extended with an integer `scale`. `geometry_of()` raises for flexible pages. Every page-receiving geometry call site is routed explicitly and pinned by a ratchet test.

**Tech Stack:** Python 3, Pydantic 2 (`>=2.10`, so there is no `serialize_by_alias`), FastAPI, pytest. No new dependencies.

**Spec:** docs/internal/superpowers/specs/2026-10-28-flexible-pages-design.md

## Global Constraints

- **Tests first, watched failing** (repo `CLAUDE.md` "Test quality bar"):
  - Every implement step is preceded by a failing test run whose failure reason you read: not an ImportError from a typo, not an unmocked request.
  - Never weaken an assertion.
- **Test command.** Every "run" step uses this; it is written `$PYTEST` below:
  `PYTHON_DOTENV_DISABLED=1 FIESTABOARD_OUTPUT_SEED_DIR=/private/tmp/claude-501/-Users-jeffre-workspace/2045ff4c-a837-434a-852f-ddb6d9ccdb9e/scratchpad/seed /private/tmp/claude-501/-Users-jeffre-workspace/2045ff4c-a837-434a-852f-ddb6d9ccdb9e/scratchpad/venv/bin/python3 -m pytest`
- **Storage changes go through `schema_version` migrations** (`src/pages/storage.py`):
  - Write a v6→v7 migration and bump `CURRENT_SCHEMA_VERSION` to 7.
  - No heuristics; the migration is idempotent and logs its count.
- **Grid pages are byte-identical.** Their stored dumps, API dumps, share strings and render output must not change. `tests/test_storage_kernel.py::test_pages_json_round_trips_byte_identical` keeps passing; only the golden's `schema_version` changes to 7.
- **No `output_api` 1 plugin changes.** Pixel delivery is one opaque full-frame `CanvasLayer` on `RichCells.layers`, from Phase 0's `src/led/page_frame.full_frame_layer`.
- **No new rasteriser.** Pixels are drawn only through `src/led/matrix.draw_glyph` + `paint_ops` (extended with `scale`) and `src/canvas/raster.render_content`.
  - FiestaUI golden fixtures (`tests/fixtures/fiestaui/led-golden.json`) must stay green.
  - The vendored `src/fiestaui/*` files and their `provenance.json` hashes are untouched.
- **The 3×10 floor is not referenced anywhere in `src/layout/`.**
- **Commits.** Local commits only, one per task, message `feat(layout): …` / `feat(pages): …`, ending with exactly this trailer:
  `Co-Authored-By: Claude <noreply@anthropic.com>`
- **Phase 0 seam names**, used verbatim:
  - `src/led/page_frame.py`: `full_frame_layer(frame: LedFrame) -> CanvasLayer`.
  - `src/pages/fit.py`: `PageFit(fits: bool, face: str | None, reason: str | None)` and `page_fit_for_board(page, board) -> PageFit`.
  - `src/outputs/board_profile.py`: `producible_grids(model, config)`.
  - `pages_compatible_with_board` delegates to `page_fit_for_board(...).fits`.
- **Dependency marking.**
  - Tasks 1–11 do not depend on Phase 0 and can run in parallel with it.
  - Tasks 12–18 depend on Phase 0 having landed. They edit `src/main.py`'s send path, `src/pages/fit.py` and `src/led/page_frame.py`, which Phase 0 creates or changes. Rebase onto Phase 0 before starting Task 12.

## Review Focus

Five likely real-world inputs and failure modes that no task's tests cover yet. Each now has a test added to its owning task, marked **[RF-n]**.

1. **A plugin is unavailable, or a variable expands to `???` or to an empty string.**
   - A clock block whose plugin errors must still lay out.
   - An empty-after-expansion text block must take zero height with no stray gap.
   - `???` must render as text, not crash measurement.
   - Owned by Task 8 ([RF-1]).
2. **Characters the board can't draw** (`é`, emoji, lowercase on an uppercase-only set). The frame and the hidden cells must show the same fallback: charset fallback is applied before measuring. Otherwise `matches_frame` and readback text disagree with the pixels. Owned by Task 6 ([RF-2]).
3. **One unbreakable long word** (a URL or a station name) with `overflow: wrap` on a 32×8 strip.
   - It must break mid-word at a glyph boundary.
   - When only one line fits, it must truncate with the ellipsis glyph and a `truncated` issue.
   - It must not loop forever or emit an empty frame.
   - Owned by Task 7 ([RF-3]).
4. **Colour expressions in the formats plugins actually emit.** `{{weather.temp_color}}` may yield `red`, `{63}`, `63`, `#FF8800`, `#ff8800` or `???`. Each must resolve or produce a `color_invalid` issue; none may raise. Owned by Task 5 ([RF-4]).
5. **Dedupe on a clock page.**
   - Identical inputs must produce byte-identical frames and an identical `content_key()`, so there is no resend every tick.
   - A one-minute change must change the key.
   - The render fingerprint must differ between two boards of the same grid but a different face or display key.
   - Owned by Task 15 ([RF-5]).

### File Structure

```text
src/layout/__init__.py          public API re-exports
src/layout/issues.py            LayoutIssue, LayoutIssueModel, issue codes
src/layout/fonts.py             FontFace, FontFamily, SizedFace, FONT_FAMILIES, size ladder, named sizes
src/layout/style.py             ResolvedStyle, ResolvedLayout, resolve_block_style(), board_style_for() hook, resolve_color_value()
src/layout/target.py            FlexTarget, flex_target_for(board, display)
src/layout/expand.py            ExpandedBlock, FillSpec, expand_blocks() (template expansion + if + fill sentinels)
src/layout/measure.py           LineItem, measure(), wrap/fit (fit_text)
src/layout/stack.py             Rect, StackResult, stack()  -- (blocks, styles, rect) -> frame ops
src/layout/pixels.py            draw_line(), canvas block raster, frame_from_ops()
src/layout/cells.py             CellLayout, layout_cell_grid()  -- reused by Phase 2
src/layout/engine.py            FlexRender, layout_flexible_page()  -- the entry point
src/layout/refs.py              flexible_plugin_ids(page)
src/pages/flexible.py           Pydantic: BlockStyle, PageStyle, FlexLayout, CanvasBlockBody, Block, FlexTargets
src/pages/models.py             Page/PageCreate/PageUpdate/PageImportPreview gain flexible fields; preview responses gain layout_issues
src/pages/storage.py            v6 -> v7 migration, CURRENT_SCHEMA_VERSION = 7
src/pages/share.py              SHARE_VERSION_FLEXIBLE = 2
src/pages/service.py            render dispatch, page_plugin_ids, batch/delete routing
src/pages/fit.py                (Phase 0 file) flexible branch + targets
src/pages/routes.py             preview responses, unsaved flexible render route, routed call sites
src/devices.py                  FlexiblePageGeometryError, geometry_of guard, page_size_key/page_size_label, pages_compatible delegate
src/led/matrix.py               draw_glyph(scale=), public cell_for_token, monochrome_rgba
src/displays/service.py         DisplayResult.layout_issues
src/main.py                     send/silence/fingerprint routing
src/templates/engine.py         public resolve_fill(text, width)
src/markup.py                   public map_text_case(line, fn)
tests/layout/...                unit tests, goldens (tests/golden/layout/*.json), call-site ratchet
docs/reference/api-endpoints.md flexible pages documented (the API "changelog" entry)
web/src/lib/api/shared.ts       PageType gains "flexible" (tolerance only)
```

### Task 1: Flexible page model

**Files:**

- Create `src/pages/flexible.py`.
- Modify `src/pages/models.py`: `PageType` at line 41, `Page` at 121, `PageCreate` at 280, `PageUpdate` at 336, `PageImportPreview` at 461, `CurrentDisplayResponse` at 642.
- Test: `tests/layout/__init__.py`, `tests/layout/test_flexible_model.py`.

**Interfaces:**

- Produces, for Phases 2–5:
  - `PageType = Literal["single", "composite", "template", "flexible"]`.
  - `src/pages/flexible.py`:
    - `class BlockStyle(ExtensibleDocument)`, with all fields optional:
      - `font: str | None`;
      - `size: Literal["small","medium","large","xlarge","fit"] | int | None` (int 1–256 px);
      - `color: str | None` and `background: str | None` (a named board colour, `#rrggbb`, or one `{{…}}`);
      - `align: Literal["left","center","right"] | None`;
      - `case: Literal["as-is","upper","lower"] | None`;
      - `overflow: Literal["wrap","shrink","ellipsis","scroll"] | None`;
      - `height: Literal["auto","fill"] | int | float | None`.
      - Unknown keys are preserved as extras.
    - `class PageStyle(BlockStyle)`.
    - `class FlexLayout(ExtensibleDocument)`:
      - `kind: str = "stack"` (any string is accepted and preserved; only `stack` is built);
      - `valign: Literal["top","middle","bottom","spread"] = "top"`;
      - `gap: Literal["none","small","medium","large"] | int = "small"`.
    - `class CanvasBlockBody(ExtensibleDocument)`: `content: DocumentContent | None = None`, `source: str | None = None`.
    - `class Block(ExtensibleDocument)`:
      - `id: str`, pattern `^[A-Za-z0-9_-]{1,32}$`;
      - `kind: str` (known kinds are `text`, `canvas` and `spacer`; unknown kinds are kept);
      - `text: str | None`, `canvas: CanvasBlockBody | None`, `style: BlockStyle | None`;
      - `priority: int | None` (0–1000);
      - `if_: str | None = Field(None, alias="if")`, with `populate_by_name=True`.
    - `class FlexTargets(ExtensibleDocument)`: `technology: list[str] | None = None`, `boards: list[str] | None = None`.
    - `MAX_BLOCKS = 32`.
  - `Page`, `PageCreate` and `PageImportPreview` gain `style: PageStyle | None`, `layout: FlexLayout | None`, `blocks: list[Block] | None` and `targets: FlexTargets | None`.
  - `PageUpdate` gains the same four fields; a supplied list replaces the whole field.

- [ ] **Step 1: failing tests** in `tests/layout/test_flexible_model.py`:

```python
FLEX = {"name": "Morning", "type": "flexible",
        "blocks": [{"id": "b1", "kind": "text", "text": "{{date_time.time}}", "style": {"size": "large"}, "priority": 1},
                   {"id": "b2", "kind": "text", "text": "HI", "if": "{{weather.temp}} > 50"}]}

def test_flexible_page_validates_and_round_trips_if_alias():
    page = Page.model_validate(FLEX)
    assert page.type == "flexible" and page.blocks[1].if_ == "{{weather.temp}} > 50"
    dumped = page.model_dump()
    assert dumped["blocks"][1]["if"] == "{{weather.temp}} > 50" and "if_" not in dumped["blocks"][1]

def test_flexible_dump_has_no_grid_fields():
    dumped = Page.model_validate(FLEX).model_dump()
    for key in ("device_type", "notes_wide", "notes_tall", "grid_rows", "grid_cols", "template", "rows", "canvases"):
        assert key not in dumped

def test_grid_page_dump_has_no_flexible_fields():
    dumped = Page(name="G", type="template", template=["HI"]).model_dump()
    for key in ("style", "layout", "blocks", "targets"):
        assert key not in dumped

def test_flexible_page_rejects_template_and_explicit_device_type():
    with pytest.raises(ValidationError, match="flexible page has no"):
        Page.model_validate({**FLEX, "template": ["X"]})
    with pytest.raises(ValidationError, match="flexible page has no"):
        PageCreate.model_validate({**FLEX, "device_type": "note"})

def test_grid_page_rejects_blocks():
    with pytest.raises(ValidationError, match="only a flexible page"):
        PageCreate.model_validate({"name": "G", "type": "template", "template": ["X"], "blocks": []})

def test_duplicate_block_ids_rejected():
    with pytest.raises(ValidationError, match="duplicate block id"):
        Page.model_validate({**FLEX, "blocks": [{"id": "a", "kind": "spacer"}, {"id": "a", "kind": "spacer"}]})

def test_unknown_block_kind_and_style_property_survive_round_trip():
    raw = {**FLEX, "blocks": [{"id": "x", "kind": "progress", "value": 3, "style": {"glow": 2}}]}
    dumped = Page.model_validate(raw).model_dump()
    assert dumped["blocks"][0]["kind"] == "progress" and dumped["blocks"][0]["value"] == 3
    assert dumped["blocks"][0]["style"]["glow"] == 2

def test_unknown_layout_kind_is_preserved():
    assert Page.model_validate({**FLEX, "layout": {"kind": "regions"}}).model_dump()["layout"]["kind"] == "regions"

def test_validate_config_requires_a_block_and_text_for_text_blocks():
    assert "at least one block" in "; ".join(Page.model_validate({**FLEX, "blocks": []}).validate_config())
    bad = Page.model_validate({**FLEX, "blocks": [{"id": "a", "kind": "text"}]})
    assert any("text block 'a' needs text" in e for e in bad.validate_config())
```

- [ ] **Step 2: run** `$PYTEST tests/layout/test_flexible_model.py -q`. Expect a failure because `"flexible"` is not a valid `PageType` literal (or an `ImportError` on `src.pages.flexible`).
- [ ] **Step 3: implement.**
  - In `src/pages/flexible.py`, validate `color`/`background` lexically with `_check_color_text(value)`: a board colour name, `#rrggbb`, a tile code `63`–`71` (optionally braced), or a string that is exactly one `{{…}}`.
  - In `models.py`, add `GRID_ONLY_FIELDS = ("device_type","notes_wide","notes_tall","grid_rows","grid_cols","display_type","rows","template","line_metadata","canvases")` and `FLEXIBLE_FIELDS = ("style","layout","blocks","targets")`.
  - Add a shared `_check_page_kind(model)` called from the after-validators of `Page` and `PageCreate`:
    - A flexible page must have every grid-only field `None`, except `device_type`/`notes_*`. For those, reject only if the name is in `model_fields_set` (message: `"A flexible page has no {field}: it fits every board"`).
    - A non-flexible page must have every flexible field `None`.
    - Block ids are unique, and there are at most `MAX_BLOCKS`.
  - `Page._normalize_grid` must skip `_check_canvases_fit` for flexible pages.
  - Add `@field_serializer("blocks")`, which dumps each block with `by_alias=True, exclude_unset=True` (the same precedent as `_dump_canvases`).
  - Add a `@model_serializer(mode="wrap")` on `Page`, `PageCreate` and `PageImportPreview`. It pops `FLEXIBLE_FIELDS` when `type != "flexible"` and pops `GRID_ONLY_FIELDS` when `type == "flexible"`.
  - In `validate_config`, add a `flexible` branch: at least one block; text blocks need `text` (a string); canvas blocks need `canvas.content` or `canvas.source`.
  - `document_protocol` returns `"page-document-v2"` for flexible pages. Widen the return annotation to `Literal["page-document-v1","page-document-v2"]`.
- [ ] **Step 4: run** the new tests, then confirm the old ones are unchanged: `$PYTEST tests/layout/test_flexible_model.py tests/test_pages.py tests/test_page_document_preservation.py tests/test_storage_kernel.py -q`. The storage kernel byte-identical test must still pass at this point.
- [ ] **Step 5: commit** `feat(pages): flexible page model with blocks, style, layout and targets`.

### Task 2: Schema v7 migration and share strings

**Files:**

- Modify `src/pages/storage.py`: lines 22 and 218–245.
- Modify `src/pages/share.py`.
- Modify `tests/golden/storage/pages.json`: `schema_version` becomes 7, and nothing else.
- Test: `tests/layout/test_flexible_storage.py`.

**Interfaces:** Produces `_migrate_v6_to_v7(pages_data: list[dict]) -> int` (returns 0), `CURRENT_SCHEMA_VERSION = 7`, `SHARE_VERSION = 1` (grid) and `SHARE_VERSION_FLEXIBLE = 2`.

Share decision: a flexible page encodes with `v: 2`. Grid pages stay `v: 1`, so older builds keep importing grid shares, and an older build refuses a flexible share with its existing `"requires FiestaBoard v2 or later"` message instead of a Pydantic error.

- [ ] **Step 1: failing tests:**

```python
def test_v6_file_migrates_to_v7_without_touching_pages(tmp_path):
    path = tmp_path / "pages.json"
    page = {"id": "p1", "name": "G", "type": "template", "template": ["HI"], "device_type": "flagship", "canvases": None}
    path.write_text(json.dumps({"schema_version": 6, "pages": [dict(page)]}))
    storage = PageStorage(storage_file=str(path))
    data = json.loads(path.read_text())
    assert data["schema_version"] == 7
    assert storage.get("p1").template == ["HI"]
    assert _migrate_v6_to_v7([dict(page)]) == 0

def test_flexible_page_survives_save_and_reload(tmp_path):
    s = PageStorage(storage_file=str(tmp_path / "pages.json"))
    created = s.create(Page.model_validate(FLEX))
    again = PageStorage(storage_file=str(tmp_path / "pages.json")).get(created.id)
    assert again.type == "flexible" and [b.id for b in again.blocks] == ["b1", "b2"]

def test_v8_file_is_refused_not_mangled(tmp_path):  # JsonStore refuses newer files
    path = tmp_path / "pages.json"; path.write_text(json.dumps({"schema_version": 8, "pages": []}))
    with pytest.raises(Exception, match="newer"):
        PageStorage(storage_file=str(path))

def test_flexible_share_uses_envelope_v2_and_grid_stays_v1():
    assert _envelope(encode_page(Page.model_validate(FLEX)))["v"] == 2
    assert _envelope(encode_page(Page(name="G", type="template", template=["X"])))["v"] == 1

def test_v2_share_round_trips_to_page_create():
    data = decode_page(encode_page(Page.model_validate(FLEX)))
    assert PageCreate.model_validate(data).type == "flexible"
```

- Before writing `test_v8_file_is_refused_not_mangled`, check the exact refusal type and message in `src/storage` (the `JsonStore` kernel), and assert that exact type.
- [ ] **Step 2: run** `$PYTEST tests/layout/test_flexible_storage.py -q`. Expected failures: `schema_version == 6`, and the envelope `v` is 1.
- [ ] **Step 3: implement.**
  - `_migrate_v6_to_v7`: its docstring says "no-op; the bump makes older builds refuse a file holding flexible pages". It logs `Pages migration v6 -> v7: 0 page(s)` and returns 0. Append `(7, _migrate_v6_to_v7)` to `MIGRATIONS`.
  - In `encode_page`, set `v = SHARE_VERSION_FLEXIBLE if page.type == "flexible" else SHARE_VERSION`.
  - In `decode_page`, accept `v <= SHARE_VERSION_FLEXIBLE`.
  - Update the golden `schema_version` to 7.
- [ ] **Step 4: run** `$PYTEST tests/layout/test_flexible_storage.py tests/test_pages.py tests/test_storage_kernel.py tests/test_config_schema_version.py -q`.
- [ ] **Step 5: commit** `feat(pages): schema v7 for flexible pages; flexible share strings are envelope v2`.

### Task 3: Geometry guard, size labels and call-site ratchet (parallel with Phase 0)

**Files:**

- Modify `src/devices.py`: `geometry_of` at 854, plus new helpers next to it.
- Create `tests/layout/geometry_call_sites.json` and `tests/layout/test_geometry_call_sites.py`.

**Interfaces:**

- Produces:
  - `class FlexiblePageGeometryError(TypeError)`. It is deliberately not a `ValueError`: `size_key`, `_scale_canvases_on_retarget`, `display_profile_for_board` and others catch `ValueError` and would silently fall back to flagship.
  - `geometry_of(obj)` raises it when `get("type") == "flexible"`. Board dicts and `BoardInstance` have no `type`, so boards are unaffected.
  - `is_flexible_page(obj) -> bool`.
  - `page_size_key(page) -> str | None` (`None` for flexible).
  - `page_size_label(page) -> str` (`"flexible"` or the size key), for log and error copy.

- [ ] **Step 1: failing tests:**

```python
def test_geometry_of_raises_for_flexible_page():
    with pytest.raises(FlexiblePageGeometryError):
        geometry_of(Page.model_validate(FLEX))

def test_geometry_of_raises_for_flexible_page_dict():
    with pytest.raises(FlexiblePageGeometryError):
        geometry_of({"type": "flexible", "name": "x"})

def test_flexible_geometry_error_escapes_value_error_handlers():
    assert not issubclass(FlexiblePageGeometryError, ValueError)

def test_dimensions_of_raises_too():
    with pytest.raises(FlexiblePageGeometryError):
        dimensions_of(Page.model_validate(FLEX))

def test_board_dicts_still_resolve():
    assert geometry_of({"device_type": "note"}).device_type == "note"

def test_size_helpers():
    assert page_size_key(Page.model_validate(FLEX)) is None
    assert page_size_label(Page.model_validate(FLEX)) == "flexible"
    assert page_size_key(Page(name="G", type="template", template=["X"])) == "flagship:6x22"

def test_every_geometry_call_site_is_classified():
    found = scan_call_sites(Path("src"))      # AST: {f"{relpath}::{enclosing_def}::{callee}"}
    manifest = json.loads(MANIFEST.read_text())
    assert found - manifest.keys() == set(), "classify the new call site in geometry_call_sites.json"
    assert manifest.keys() - found == set(), "remove stale entries"

def test_every_page_routed_site_names_an_existing_test():
    for site, entry in json.loads(MANIFEST.read_text()).items():
        if entry["kind"] == "page":
            assert entry.get("test") and test_exists(entry["test"]), site
```

- [ ] **Step 2: run** `$PYTEST tests/layout/test_geometry_call_sites.py -q`. Expected failures: `ImportError` on `FlexiblePageGeometryError`, then an empty manifest.
- [ ] **Step 3: implement.**
  - Add the guard as the first statement of `geometry_of`.
  - `scan_call_sites` walks `ast` for `Call` nodes whose func name is in `{"geometry_of","size_key","dimensions_of","pages_compatible_with_board"}`, keyed by file plus enclosing function name. Keying on names rather than line numbers avoids churn.
  - Seed the manifest. Each entry is `{"kind": "board"|"page"|"tuple", "test": "tests/...::test_name"|null}`.
  - **Board-only sites** (`kind: "board"`):
    - `src/main.py::_board_size_key` and `_silence_geometry`;
    - `src/display_runtime.py`;
    - `src/mcp_server.py` (159, 271);
    - `src/board_guards.py`;
    - `src/v1/routes_meta.py`, `src/v1/routes_boards.py` (275, 319, 612);
    - `src/settings/routes.py` (1174, 1195, 1354);
    - `src/plugins/previews.py`;
    - `src/panels/geometry.py`, `src/panels/reconcile.py`;
    - `src/board_api/routes.py`, `src/displays/routes.py`;
    - `src/ai/prompt_builder.py:493`, `src/ai/page_routes.py:732`;
    - `src/ops/executors.py:860`;
    - `src/templates/routes.py` (328, 502);
    - `src/mqtt/commands.py`;
    - `src/outputs/display_profile.py`, `src/outputs/description.py`, `src/outputs/board_profile.py`, `src/outputs/first_party.py`;
    - `src/pages/routes.py:487`;
    - `src/pages/service.py:1096`.
  - **Tuple sites** (`kind: "tuple"`): `src/pages/service.py::shared_context_for` at 517.
  - **Page sites** (`kind: "page"`) start with `test: null`, and the second test is marked `xfail(strict=True)` until Task 14 fills them in. Task 14 removes the xfail.
- [ ] **Step 4: run** `$PYTEST tests/layout/test_geometry_call_sites.py tests/test_devices.py tests/test_page_board_compatibility.py -q`.
- [ ] **Step 5: commit** `feat(devices): geometry_of refuses flexible pages; call-site ratchet`.

### Task 4: Font registry as families, plus integer scaling in the rasteriser (parallel)

**Files:**

- Create `src/layout/__init__.py` and `src/layout/fonts.py`.
- Modify `src/led/matrix.py`: `draw_glyph` at 442; add `cell_for_token` (a public alias of `_cell_for_token` at 747) and `monochrome_rgba` (a public alias of `_monochrome_rgba` at 622); update `__all__`.
- Test: `tests/layout/test_fonts.py`.

**Interfaces:**

- `@dataclass(frozen=True) class FontFace`:
  - `id: str` (the vendored id, `"3x5"`);
  - `kind: Literal["bitmap","outline"]`;
  - `pixel_height: int`, `glyph_width: int`, `spacing_x: int`, `spacing_y: int`;
  - `led_font: LedFont`.
- `@dataclass(frozen=True) class FontFamily`: `id: str`, `name: str`, `faces: tuple[FontFace, ...]` (ascending by height).
- `@dataclass(frozen=True) class SizedFace`: `face: FontFace`, `scale: int`. Properties:
  - `height = face.pixel_height * scale`;
  - `advance = (glyph_width + spacing_x) * scale`;
  - `gutter = spacing_x * scale`;
  - `line_gap = spacing_y * scale`.
- `FONT_FAMILIES: Mapping[str, FontFamily]` (`{"fiesta": …}`), `DEFAULT_FONT_FAMILY = "fiesta"`, `MAX_TEXT_SCALE = 8`.
- `size_ladder(family) -> tuple[SizedFace, ...]`. These are bitmap faces only, `scale` 1..8, deduplicated by height (on a tie, prefer the larger face at the smaller scale), sorted by height.
  - For `fiesta`, the heights are 5, 7, 10, 14, 15, 20, 21, 25, 28, 30, 35, 40, 42, 49 and 56.
- `face_for_height(family, px) -> tuple[SizedFace, bool]`: the largest ladder entry ≤ px, and whether it is exact. Below the smallest, it returns `(smallest, False)`.
- `face_for_led_font(font_id: str) -> FontFace`.
- `NAMED_SIZES = ("small","medium","large","xlarge")`.
- `named_size_heights(*, surface_height: int, default_height: int, family) -> dict[str, int]`.
- `draw_glyph(ops, key, x, y, face, color, options, *, scale: int = 1)`. At scale > 1, glyph rows are scaled with a cached `scaled_rows(rows, scale)` (`functools.lru_cache`), and tile rects use `w=glyph_width*scale, h=glyph_height*scale`.

**Proposed named-size scale.** Rules:

- `small` = the family's smallest face height.
- `medium` = the board's default face height: 3x5 gives 5, 5x7 gives 7, and no LED face gives 7.
- `large` = max(`ladder_floor(H/4)`, `ladder_next(medium)`). If that exceeds H, it is `medium`.
- `xlarge` = max(`ladder_floor(H/2)`, `ladder_next(large)`). If that exceeds H, it is `large`.

| Golden device | H | small | medium | large | xlarge |
|---|---|---|---|---|---|
| Pixoo 64 @3x5 | 64 | 5 | 5 | 15 | 30 |
| Pixoo 64 @5x7 | 64 | 5 | 7 | 15 | 30 |
| 32×8 strip (AWTRIX, 3x5) | 8 | 5 | 5 | 7 | 7 |
| MAX7219 32×8 mono (3x5) | 8 | 5 | 5 | 7 | 7 |
| HUB75 64×32 (5x7) | 32 | 5 | 7 | 10 | 15 |
| FiestaPanel LED 192×96 (5x7) | 96 | 5 | 7 | 21 | 42 |
| Flagship (cells) | n/a | one character size; any size other than `medium` is reported as `size_ignored` (Task 9) | | | |

- [ ] **Step 1: failing tests:**

```python
def test_fiesta_family_maps_the_two_vendored_faces():
    fam = FONT_FAMILIES["fiesta"]
    assert [(f.id, f.pixel_height, f.kind) for f in fam.faces] == [("3x5", 5, "bitmap"), ("5x7", 7, "bitmap")]

def test_ladder_heights():
    assert [s.height for s in size_ladder(FONT_FAMILIES["fiesta"])][:8] == [5, 7, 10, 14, 15, 20, 21, 25]

def test_face_for_height_exact_and_rounded_down():
    sf, exact = face_for_height(FONT_FAMILIES["fiesta"], 14); assert (sf.face.id, sf.scale, exact) == ("5x7", 2, True)
    sf, exact = face_for_height(FONT_FAMILIES["fiesta"], 12); assert (sf.face.id, sf.scale, exact) == ("3x5", 2, False)
    sf, exact = face_for_height(FONT_FAMILIES["fiesta"], 3);  assert (sf.face.id, sf.scale, exact) == ("3x5", 1, False)

@pytest.mark.parametrize("h,default,expected", [(64, 5, (5, 5, 15, 30)), (64, 7, (5, 7, 15, 30)), (8, 5, (5, 5, 7, 7)),
                                                 (32, 7, (5, 7, 10, 15)), (96, 7, (5, 7, 21, 42))])
def test_named_size_scale(h, default, expected):
    s = named_size_heights(surface_height=h, default_height=default, family=FONT_FAMILIES["fiesta"])
    assert (s["small"], s["medium"], s["large"], s["xlarge"]) == expected

def test_draw_glyph_scale_2_doubles_every_pixel():
    ops = []; draw_glyph(ops, "A", 0, 0, LED_FONTS["3x5"], "#ffffff", LedRenderOptions(), scale=2)
    rows = ops[0].rows; base = LED_FONTS["3x5"].glyphs["A"]
    assert len(rows) == 10 and rows[0] == "".join(c * 2 for c in base[0]) and rows[1] == rows[0]

def test_draw_glyph_scale_tile_rect():
    ops = []; draw_glyph(ops, "tile:63", 0, 0, LED_FONTS["5x7"], "#fff", LedRenderOptions(), scale=3)
    assert (ops[0].w, ops[0].h) == (15, 21)
```

- [ ] **Step 2: run** `$PYTEST tests/layout/test_fonts.py -q`. Expected failure: `ModuleNotFoundError: src.layout`.
- [ ] **Step 3: implement** as specified above. The registry is built from `LED_FONTS` and never reads the JSON directly, so the vendored hashes are untouched.
- [ ] **Step 4: run** `$PYTEST tests/layout/test_fonts.py tests/test_led_*.py tests/test_fiestaui*.py -q`. The FiestaUI golden must stay green (`grep -l led-golden tests/*.py` finds the file).
- [ ] **Step 5: commit** `feat(layout): font registry as families with integer scaling`.

### Task 5: Layout issues and the style resolver (parallel)

**Files:**

- Create `src/layout/issues.py`, `src/layout/style.py` and `src/layout/target.py`.
- Test: `tests/layout/test_style.py`.

**Interfaces** (consumed by Phases 2–5):

- `@dataclass(frozen=True) class LayoutIssue`:
  - `path: tuple[str, ...]` (e.g. `("blocks","b2","style","size")`; a later `regions` kind prefixes `("regions","r1")`);
  - `code: str`;
  - `severity: Literal["info","warning"]`;
  - `message: str`;
  - `to_json() -> {"path": [...], "code", "severity", "message"}`.
- `class LayoutIssueModel(BaseModel)` with the same four fields, for responses.
- `ISSUE_CODES`:
  - style codes: `font_unavailable`, `size_rounded`, `size_too_small`, `size_ignored`, `color_invalid`, `color_dropped`, `background_dropped`, `case_unsupported`, `overflow_unsupported`, `style_unknown`;
  - block codes: `block_kind_unsupported`, `layout_kind_unsupported`, `if_failed`;
  - fit and stack codes: `wrapped`, `shrunk`, `ellipsized`, `truncated`, `dropped`, `canvas`, `canvas_not_drawn`, `surface_too_small`.
- `@dataclass(frozen=True) class FlexTarget`:
  - `rows: int`, `cols: int` (the board's current grid);
  - `display: DisplayProfile | None`;
  - `board_style: Mapping[str, Any] = MappingProxyType({})`;
  - properties: `pixels` (`display` supports `"pixels"`), `width`, `height`, `mixed_case`, `color_model` (`"rgb"|"mono"|"tiles"`), `monochrome`, `default_face_id`.
- `flex_target_for(board: Mapping | None, display: DisplayProfile | None) -> FlexTarget`. Rows and cols come from `display.rows/cols` when set, else `dimensions_of(board)`, else flagship 6×22.
- `board_style_for(board: Mapping | None) -> Mapping[str, Any]`. In Phase 1 it returns `MappingProxyType({})`; this is the Phase 3 hook.
- `@dataclass(frozen=True) class ResolvedStyle`:
  - `family: str`, `sized: SizedFace | None` (`None` on cell targets), `px: int`;
  - `color: str | None`, `background: str | None` (lowercase `#rrggbb`);
  - `align`, `case`, `overflow`;
  - `height: Literal["auto","fill"] | int | float`;
  - `fit: bool` (the size was `fit`).
- `@dataclass(frozen=True) class ResolvedLayout`: `kind: str`, `valign`, `gap_px: int`.
- `device_default_style(target) -> dict`.
- `resolve_color_value(value: str, context: Mapping, *, engine) -> str | None`. It accepts a board colour name, `63`–`71` with or without braces, and `#rrggbb` with whitespace trimmed and case folded. A `{{…}}` expression is rendered first.
- `resolve_block_style(levels: Sequence[Mapping[str, Any]], target: FlexTarget, context: Mapping, *, path: tuple[str, ...], engine=None) -> tuple[ResolvedStyle, list[LayoutIssue]]`. The cascade order is `[device_default_style(target), target.board_style, page.style, block.style]`, lowest first; `None` levels are skipped.
- `resolve_layout(layout: FlexLayout | None, *, path) -> tuple[ResolvedLayout, list[LayoutIssue]]`. Gap px values: none 0, small 1, medium 2, large 4, or the int given. A kind other than `stack` gives a `layout_kind_unsupported` warning and is laid out as a stack.

Resolution rules (spec section 3):

- **Font:** the requested family; else the board-style family; else `fiesta`. Each miss is a `font_unavailable` warning.
- **Size:** named sizes go through `named_size_heights`. An exact px is looked up with `face_for_height`: an inexact match is `size_rounded` (info); a request below 5 px is `size_too_small` (warning). On cell targets any non-`medium` size is `size_ignored` (info).
- **Colour:**
  - `rgb`: as given.
  - `mono`: non-black (`led_monochrome_lit`) becomes the panel colour; black becomes unlit.
  - `tiles`: text colour is dropped (`color_dropped`); background is dropped in Phase 1 (`background_dropped`). Nearest-tile mapping is Phase 2.
  - An unparseable colour is `color_invalid`.
- **Case:** `lower` on a board without `mixed_case` gives `case_unsupported` and renders upper.
- **Overflow:** `scroll` gives `overflow_unsupported` and falls back to `ellipsis`. The default overflow is `wrap`.
- **Unknown style keys** (extras) give `style_unknown` (info) and are preserved.

- [ ] **Step 1: failing tests**, including **[RF-4]**:

```python
PIXOO = FlexTarget(rows=10, cols=16, display=profile("divoom_pixoo64", font="3x5"))
STRIP_MONO = FlexTarget(rows=1, cols=8, display=profile("max7219_4in1"))
FLAGSHIP = FlexTarget(rows=6, cols=22, display=None)

def test_cascade_block_beats_page_beats_board_beats_device():
    s, _ = resolve_block_style([{"color": "#111111"}, {"color": "#222222"}, {"color": "#333333"}], PIXOO, {}, path=("blocks","b1"))
    assert s.color == "#333333"
    s, _ = resolve_block_style([{"align": "right"}, None, {}], PIXOO, {}, path=("blocks","b1"))
    assert s.align == "right"

def test_board_style_level_is_honoured_when_present():
    t = replace(PIXOO, board_style={"color": "#00ff00"})
    s, _ = resolve_block_style([t.board_style], t, {}, path=("blocks","b1")); assert s.color == "#00ff00"

def test_named_large_on_pixoo_3x5_is_3x5_times_3():
    s, issues = resolve_block_style([{"size": "large"}], PIXOO, {}, path=("blocks","b1"))
    assert (s.sized.face.id, s.sized.scale, s.px) == ("3x5", 3, 15) and issues == []

def test_exact_12px_rounds_down_with_issue():
    s, issues = resolve_block_style([{"size": 12}], PIXOO, {}, path=("blocks","b1"))
    assert s.px == 10 and [i.code for i in issues] == ["size_rounded"] and issues[0].path == ("blocks","b1","style","size")

def test_unknown_font_falls_back_with_issue():
    s, issues = resolve_block_style([{"font": "comic"}], PIXOO, {}, path=("blocks","b1"))
    assert s.family == "fiesta" and issues[0].code == "font_unavailable"

def test_mono_colour_maps_to_panel_and_black_stays_unlit(): ...
def test_tiles_drop_text_colour_with_issue():
    _, issues = resolve_block_style([{"color": "red"}], FLAGSHIP, {}, path=("blocks","b1"))
    assert issues[0].code == "color_dropped"

def test_lower_on_uppercase_only_board_reports_and_uppercases(): ...
def test_scroll_falls_back_to_ellipsis(): ...

@pytest.mark.parametrize("raw,expected", [("red", "#eb4034"), ("{63}", "#eb4034"), ("63", "#eb4034"),
                                          ("#FF8800", "#ff8800"), ("#ff8800 ", "#ff8800"), ("???", None)])
def test_color_expression_formats_plugins_emit(raw, expected):          # [RF-4]
    ctx = {"weather": {"temp_color": raw}}
    s, issues = resolve_block_style([{"color": "{{weather.temp_color}}"}], PIXOO, ctx, path=("blocks","b1"))
    assert s.color == (expected or DEFAULT_LED_TEXT_COLOR)
    assert (expected is None) == any(i.code == "color_invalid" for i in issues)
```

- The `profile(model_id, font=None)` test helper goes in `tests/layout/devices.py`. It builds a `DisplayProfile` through `src.outputs.display_profile._profile(model_with_led_font(model, font), model_character_set(model), None, grid)` from `builtin_device_models()` / `fiestapanel_model("led_matrix", 12, 32)`.
- [ ] **Step 2: run** `$PYTEST tests/layout/test_style.py -q`. Expected failure: `ModuleNotFoundError`.
- [ ] **Step 3: implement.** `resolve_color_value` evaluates expressions with `engine.render(value, context, extended_markup=True)` and then normalises using `src.led.matrix.BOARD_COLORS` and the tile-code mapping. Expose `color_code_to_hex(code)` as a public wrapper of `_color_code_to_hex` in `matrix.py`.
- [ ] **Step 4: run** `$PYTEST tests/layout/test_style.py -q`.
- [ ] **Step 5: commit** `feat(layout): style cascade resolver and layout issues`.

### Task 6: Expansion with fill markers, `if`, case and charset fallback (parallel)

**Files:**

- Create `src/layout/expand.py` and `src/layout/refs.py`.
- Modify `src/templates/engine.py`: add public `resolve_fill(text, width, *, extended_markup=True) -> str`, delegating to `_process_fill_space` at 1877.
- Modify `src/markup.py`: add public `map_text_case(line: str, fn: Callable[[str], str]) -> str`, built on `_pieces`/`_serialize` so markup survives.
- Test: `tests/layout/test_expand.py`.

**Interfaces:**

- `FILL_SENTINEL_BASE = 0xE000`.
- `@dataclass(frozen=True) class FillSpec`: `pattern: str | None` (`None` is a blank fill).
- `@dataclass(frozen=True) class ExpandedBlock`:
  - `id`, `kind`, `index: int`, `priority: int | None`;
  - `markup: str` (fills as sentinels U+E000+i);
  - `fills: tuple[FillSpec, ...]`;
  - `tokens: tuple[BoardToken, ...]` (parsed with `extended_markup=True` and the board's case, then charset fallback applied);
  - `block: Block`.
- `expand_blocks(page: Page, target: FlexTarget, context: Mapping, styles: Mapping[str, ResolvedStyle], *, engine=None) -> tuple[list[ExpandedBlock], list[LayoutIssue]]`.
- `markup_with_fills(block: ExpandedBlock, text_fill: Callable[[FillSpec], str]) -> str`, used by the cell layout to turn sentinels back into `\x00FILL_SPACE…\x00` markers for `resolve_fill`.
- `flexible_plugin_ids(page) -> set[str] | None`, the union of:
  - `extract_template_plugin_ids` over text blocks;
  - each `if` wrapped as `{{…}}`;
  - each style `{{…}}` colour;
  - `canvas_plugin_ids` over a synthetic `Canvas` for each canvas block.

Rules:

- Text is expanded with `engine.render(text, context, extended_markup=True)` only, never `render_lines`.
- An `if` is evaluated with `engine.evaluate_expression(body, context)` and truthiness `src.canvas.evaluate._truthy`. Promote it to public `truthy` and keep the alias.
  - A falsy result hides the block silently.
  - A `FormulaError` hides it with an `if_failed` warning.
- Unknown block kinds give `block_kind_unsupported` (warning) and are skipped.
- Case is applied per style (`upper`/`lower`, or forced `upper` when the board is not `mixed_case`).
- Tokens pass through `charset_fallback(CharsetLookup(display.character_set), token)` exactly as `project_message` does, so pixels and cells agree.

- [ ] **Step 1: failing tests**, including **[RF-2]**:

```python
def test_expansion_uses_render_not_render_lines(monkeypatch):
    engine = get_template_engine(); monkeypatch.setattr(engine, "render_lines", lambda *a, **k: pytest.fail("grid render"))
    blocks, _ = expand_blocks(page_with("{{x.y}} OK"), PIXOO, {"x": {"y": "72"}}, STYLES, engine=engine)
    assert "".join(t.value for t in blocks[0].tokens) == "72 OK"

def test_fill_space_becomes_sentinel_not_padding():
    b, _ = expand_blocks(page_with("A{{fill_space}}B"), PIXOO, {}, STYLES)
    assert b[0].fills == (FillSpec(None),) and chr(0xE000) in b[0].markup

def test_fill_inside_colour_span_keeps_span_on_both_sides():
    b, _ = expand_blocks(page_with("{red:A{{filled:-}}B}"), PIXOO, {}, STYLES)
    assert b[0].tokens[0].color and b[0].tokens[-1].color and b[0].fills == (FillSpec("-"),)

def test_false_if_hides_block_silently_and_error_reports():
    shown, issues = expand_blocks(page_with("HI", if_="{{= 1 > 2 }}"), PIXOO, {}, STYLES); assert shown == [] and issues == []
    shown, issues = expand_blocks(page_with("HI", if_="{{= NOPE( }}"), PIXOO, {}, STYLES)
    assert shown == [] and issues[0].code == "if_failed" and issues[0].path == ("blocks","b1","if")

def test_unsupported_characters_fall_back_identically_to_cells():          # [RF-2]
    b, _ = expand_blocks(page_with("café ✨ ok"), FlagshipRich := FLAGSHIP, {}, STYLES)
    projected = project_message(b[0].markup.replace(chr(0xE000), ""), 1, 22, None)
    assert [t.flap_code for t in b[0].tokens] == projected.characters[0][: len(b[0].tokens)]

def test_flexible_plugin_ids_cover_text_if_colour_and_canvas():
    assert flexible_plugin_ids(page_with("{{weather.temp}}", if_="{{stocks.up}}", color="{{air.color}}")) == {"weather", "stocks", "air"}
```

- Add a Pixoo variant of the [RF-2] test with `mixed_case`: `é` (not in `led_3x5`) must be the set's fallback in both the tokens and `project_message(..., display.character_set)`.
- [ ] **Step 2: run** `$PYTEST tests/layout/test_expand.py -q`. Expected: `ModuleNotFoundError`.
- [ ] **Step 3: implement** as specified.
- [ ] **Step 4: run** `$PYTEST tests/layout/test_expand.py tests/test_templates*.py tests/test_markup*.py -q`.
- [ ] **Step 5: commit** `feat(layout): block expansion with pixel fill markers and conditions`.

### Task 7: Measure and fit (wrap, shrink, ellipsis) (parallel)

**Files:**

- Create `src/layout/measure.py`.
- Test: `tests/layout/test_fit.py`.

**Interfaces:**

- `LineItem = Glyph(token: BoardToken) | Gap(px: int)`.
- `@dataclass(frozen=True) class FittedText`:
  - `lines: tuple[tuple[LineItem, ...], ...]`;
  - `sized: SizedFace`;
  - `width: int` (the widest line), `height: int`;
  - `issues: tuple[LayoutIssue, ...]`.
- `measure(items, sized) -> int`. Every glyph, icon and tile is one cell, `advance` wide. Width = `n_cells * advance - gutter` (0 when empty) plus the sum of `Gap.px`.
- `fit_text(block: ExpandedBlock, style: ResolvedStyle, width: int, max_height: int, *, family, path) -> FittedText`.

Algorithm (the body is specified because it is not determined by existing code):

```text
sized = style.sized
if style.fit: sized = largest ladder entry with height <= max_height and measure(one_line) <= width, else smallest
lines = [items]                                   # fills are zero-width while wrapping
if measure(items) > width:
    if overflow == "wrap":   lines = wrap(items, width, sized); issue wrapped(info)
    elif overflow == "shrink":
        for cand in ladder entries below sized, descending: if measure(items, cand) <= width: sized = cand; issue shrunk(info); break
        else: sized = smallest; lines=[ellipsize(items, width, sized)]; issue ellipsized(warning)
    else:  lines = [ellipsize(...)]; issue ellipsized(warning)  # "ellipsis" and scroll-fallback
max_lines = (max_height + line_gap) // (sized.height + line_gap)
if len(lines) > max_lines > 0: lines = lines[:max_lines]; lines[-1] = ellipsize(lines[-1] + [Glyph(" ")]+tail, width); issue truncated(warning)
for each line: resolve fills in pixels: avail = width - measure(non-fill); blank fills -> Gap(avail split, extra px to earlier fills);
               pattern fills -> repeat pattern glyphs floor((share + gutter) / advance) times (colour names -> tile tokens); avail <= 0 -> fills removed
height = len(lines) * sized.height + (len(lines)-1) * sized.line_gap
```

- `wrap`: greedy. Words are split at blank char tokens; a line's leading blanks are dropped. A word wider than `width` is broken at the last glyph boundary that fits. Each line holds at least one glyph, so the loop always terminates.
- `ellipsize`: keep the longest prefix such that prefix + the ellipsis glyph fits. The ellipsis glyph is `…` if the face has it, else `.`; neither vendored face has `…`, so it is `.`. Trailing blanks are trimmed before the ellipsis.

- [ ] **Step 1: failing tests**, including **[RF-3]**:

```python
S35 = SizedFace(face_for_led_font("3x5"), 1)   # advance 4, gutter 1

def test_measure_counts_cells_minus_trailing_gutter():
    assert measure(glyphs("ABC"), S35) == 11 and measure((), S35) == 0

def test_wrap_breaks_at_spaces():
    f = fit_text(block("AB CD EF"), style(overflow="wrap", sized=S35), width=19, max_height=64, family=FIESTA, path=P)
    assert texts(f) == ["AB CD", "EF"] and f.issues[0].code == "wrapped"

def test_shrink_steps_down_a_face():
    f = fit_text(block("HELLO"), style(overflow="shrink", sized=SizedFace(face_for_led_font("5x7"), 1)), width=24, max_height=64, ...)
    assert f.sized.face.id == "3x5" and f.issues[0].code == "shrunk"

def test_ellipsis_cuts_at_glyph_boundary():
    f = fit_text(block("ABCDEFG"), style(overflow="ellipsis", sized=S35), width=19, max_height=8, ...)
    assert texts(f) == ["ABC."] and f.issues[0].code == "ellipsized"

def test_unbreakable_word_on_32x8_strip_breaks_midword_then_truncates():   # [RF-3]
    f = fit_text(block("WWW.EXAMPLESTATION.COM"), style(overflow="wrap", sized=S35), width=32, max_height=8, ...)
    assert len(f.lines) == 1 and texts(f)[0].endswith(".") and measure(f.lines[0], S35) <= 32
    assert {i.code for i in f.issues} == {"wrapped", "truncated"}

def test_fit_size_picks_largest_one_line_size():
    f = fit_text(block("12:45"), style(fit=True, sized=S35), width=64, max_height=64, ...)
    assert f.sized.height == 20      # 3x5*4: 5 cells*16-4=76>64? -> expect the asserted value computed in-test from the ladder

def test_blank_fill_resolves_in_pixels():
    f = fit_text(block_with_fill("A", None, "B"), style(sized=S35), width=20, max_height=8, ...)
    assert measure(f.lines[0], S35) == 20
```

- In `test_fit_size_picks_largest_one_line_size`, compute `expected` inside the test as the largest `size_ladder` entry with `measure(...) <= 64`. Do not hard-code it unless you have verified the arithmetic.
- [ ] **Step 2: run** `$PYTEST tests/layout/test_fit.py -q`. Expected: `ModuleNotFoundError`.
- [ ] **Step 3: implement** per the algorithm above.
- [ ] **Step 4: run** `$PYTEST tests/layout/test_fit.py -q`.
- [ ] **Step 5: commit** `feat(layout): measure and fit text blocks in pixels`.

### Task 8: Stack and pixel emit (parallel)

**Files:**

- Create `src/layout/stack.py` and `src/layout/pixels.py`.
- Test: `tests/layout/test_stack.py`.

**Interfaces** (the regions-ready seam):

- `@dataclass(frozen=True) class Rect`: `x: int`, `y: int`, `w: int`, `h: int`.
- `@dataclass(frozen=True) class StackResult`:
  - `ops: tuple[LedDrawOp, ...]`;
  - `issues: tuple[LayoutIssue, ...]`;
  - `shown: tuple[str, ...]`;
  - `frame(width, height, background=None) -> LedFrame`.
- `stack(blocks: Sequence[ExpandedBlock], styles: Mapping[str, ResolvedStyle], rect: Rect, *, layout: ResolvedLayout, options: LedRenderOptions, context: Mapping, family, path: tuple[str, ...] = ()) -> StackResult`.
- `draw_line(ops, items, x, y, sized, options, text_color)`. It uses `cell_for_token` and `draw_glyph(..., scale=sized.scale)`. Block-span backgrounds are a rect per cell, joined over the gutter to a same-background neighbour.
- `canvas_block_op(block, rect, context) -> tuple[LedDrawOp | None, list[LayoutIssue]]`:
  - builds a synthetic `Canvas(id="flex", area={"row":1,"col":1,"rows":1,"cols":1}, content=…, source=…)`;
  - resolves it with `resolve_canvas`, then `render_content(resolved, rect.w, rect.h)`;
  - applies `monochrome_rgba` when the panel is mono;
  - returns a `LedDrawOp("bitmap", …)`.
  - Its `CanvasIssue`s become `canvas` issues at path `(*path,"blocks",id,"canvas",issue.path)`.
- `frame_from_ops(width, height, ops, background) -> LedFrame`. It fills the background, then calls `paint_ops`.

Algorithm (the body is specified):

```text
heights: text -> fit_text(..., width=rect.w, max_height=rect.h).height (0 if no glyphs: [RF-1]);
         spacer auto -> page-default size height; canvas auto -> rect.w*size_h//size_w if content.size else "fill";
         int -> px; float 0<f<=1 -> floor(rect.h*f); "fill" -> deferred
visible = [b for b in blocks if height != 0 or kind != "text"]
while sum(fixed heights) + gap*(len(visible)-1) > rect.h and visible:
    victim = max(visible, key=lambda b: (b.priority is None, b.priority or 0, b.index))   # unset first, then highest number, later first
    visible.remove(victim); issue dropped(warning, path=(*path,"blocks",victim.id))
fill blocks share remaining = rect.h - fixed - gaps equally (floor; extra px to earlier); a fill block with < 1 px -> dropped
total = used height; y0 by valign: top rect.y | middle rect.y+(rect.h-total)//2 | bottom rect.y+rect.h-total |
        spread: extra=(rect.h-total) distributed between blocks (single block -> middle)
text x by align within rect: left rect.x | center rect.x+(rect.w-w)//2 | right rect.x+rect.w-w
page/block background: rect op across rect.w for the block's band (page background fills rect first)
every op is clipped to rect (assert in a test, not just by construction)
```

If `rect` is smaller than the smallest face height, the result is no text ops plus a `surface_too_small` warning.

- [ ] **Step 1: failing tests**, including **[RF-1]**:

```python
def test_lowest_priority_dropped_first_with_issue(): ...  # 3 blocks of 7px on an 8px rect -> only priority 1 shown
def test_unset_priority_drops_before_explicit_and_bottom_first(): ...
def test_valign_middle_centres_the_stack():
    r = stack(two_blocks_5px, STYLES, Rect(0, 0, 64, 64), layout=ResolvedLayout("stack", "middle", 1), ...)
    assert min(op.y for op in r.ops) == (64 - 11) // 2

def test_spread_distributes_space_between_blocks(): ...
def test_fill_canvas_takes_remaining_height(): ...
def test_stack_never_draws_outside_its_rect():                # regions constraint
    r = stack(many_blocks, STYLES, Rect(10, 5, 30, 20), ...)
    lit = lit_pixels(r.frame(64, 64))
    assert lit and all(10 <= x < 40 and 5 <= y < 25 for x, y in lit)

def test_empty_and_unavailable_variable_blocks():              # [RF-1]
    r = stack(expanded(["", "???", "B"]), STYLES, Rect(0, 0, 64, 64), layout=TOP, ...)
    assert r.shown == ("b2", "b3")          # empty text takes zero height, "???" renders as text
    assert min(op.y for op in r.ops if op.kind == "glyph") == 0
```

- [ ] **Step 2: run** `$PYTEST tests/layout/test_stack.py -q`. Expected: `ModuleNotFoundError`.
- [ ] **Step 3: implement** per the algorithm above.
- [ ] **Step 4: run** `$PYTEST tests/layout/test_stack.py -q`.
- [ ] **Step 5: commit** `feat(layout): vertical stack over an arbitrary rect with priority drops`.

### Task 9: Cell layout at the board's grid (parallel; reused by Phase 2)

**Files:**

- Create `src/layout/cells.py`.
- Test: `tests/layout/test_cells.py`.

**Interfaces:**

- `@dataclass(frozen=True) class CellLayout`: `lines: tuple[str, ...]` (exactly `rows` markup lines, each ≤ `cols` tiles); `issues: tuple[LayoutIssue, ...]`.
- `layout_cell_grid(blocks: Sequence[ExpandedBlock], styles: Mapping[str, ResolvedStyle], rows: int, cols: int, *, layout: ResolvedLayout, report_styles: bool, engine=None, path: tuple[str, ...] = ()) -> CellLayout`.
  - `report_styles` is `True` when the cells are what the board shows (split-flap or integer-only).
  - It is `False` under an LED frame, where the frame already reported its compromises.

Rules:

- Each text block's markup (sentinels turned back into fill markers) is handled by `count_tiles` against `cols`:
  - fits: one row;
  - `wrap`: `markup.wrap_line(line, cols)`;
  - `shrink`: the same as wrap, plus `shrunk`-unavailable info when `report_styles`;
  - `ellipsis`: `take_tiles(line, cols - 1)[0] + "."`.
- Fills are resolved with `engine.resolve_fill(line, width=cols)` on single-row lines.
- Alignment pads with spaces by `count_tiles`.
- Spacers take one row. Canvas blocks take zero rows, with `canvas_not_drawn` when `report_styles`.
- Gaps are 0 rows.
- Priority drops and `valign` follow the same rules as Task 8, in rows.
- Rows past `rows` are dropped with `dropped`.
- Block colours are not applied in cells in Phase 1; tile mapping is Phase 2.

- [ ] **Step 1: failing tests:**

```python
def test_flagship_wraps_by_characters_and_centres():
    out = layout_cell_grid(expanded(["GOOD MORNING SUNSHINE AND FRIENDS"], align="center"), STYLES, 6, 22, layout=TOP, report_styles=True)
    assert out.lines[0] == "GOOD MORNING SUNSHINE " .rstrip().center(22)[:22] or count_tiles(out.lines[0]) <= 22
    assert len(out.lines) == 6 and all(count_tiles(l) <= 22 for l in out.lines)

def test_fill_space_in_cells_fills_the_row():
    out = layout_cell_grid(expanded(["A{{fill_space}}B"]), STYLES, 6, 22, layout=TOP, report_styles=True)
    assert out.lines[0] == "A" + " " * 20 + "B"

def test_rows_overflow_drops_lowest_priority(): ...
def test_canvas_block_reported_only_when_cells_are_what_shows(): ...
def test_colour_span_markup_survives_wrap():
    out = layout_cell_grid(expanded(["{red:HOT HOT HOT}"]), STYLES, 3, 5, layout=TOP, report_styles=True)
    assert out.lines[0].startswith("{red:") and out.lines[1].startswith("{red:")
```

- Replace the first assertion's hand-built expected string with the exact expected lines once Step 2's output is checked by eye. Keep the assertion exact: `out.lines == (...)`.
- [ ] **Step 2: run** `$PYTEST tests/layout/test_cells.py -q`. Expected: `ModuleNotFoundError`.
- [ ] **Step 3: implement** as specified.
- [ ] **Step 4: run** `$PYTEST tests/layout/test_cells.py -q`.
- [ ] **Step 5: commit** `feat(layout): character-grid cell layout for flexible pages`.

### Task 10: Engine entry point (parallel)

**Files:**

- Create `src/layout/engine.py`, and fill in `src/layout/__init__.py` re-exports.
- Test: `tests/layout/test_engine.py`.

**Interfaces** (the layout entry point Phases 2–5 call):

- `@dataclass(frozen=True) class FlexRender`:
  - `frame: LedFrame | None` (pixel targets only);
  - `cell_lines: tuple[str, ...]`;
  - `issues: tuple[LayoutIssue, ...]` (frame issues first, then cell issues, de-duplicated by `(path, code)`);
  - `shown: tuple[str, ...]`.
- `layout_flexible_page(page: Page, target: FlexTarget, context: Mapping[str, Any], *, engine: TemplateEngine | None = None) -> FlexRender`. The flow:
  1. `resolve_layout`;
  2. per block, `resolve_block_style([device_default_style(target), target.board_style, page.style, block.style], ...)`;
  3. `expand_blocks`;
  4. if `target.pixels`: `stack(..., Rect(0, 0, target.width, target.height), options=LedRenderOptions(monochrome=target.monochrome, glyphs=charset glyphs, tile_gap=display.tile_gap or "gap"))`, then `.frame(width, height, page background)`;
  5. always `layout_cell_grid(..., target.rows, target.cols, report_styles=not target.pixels)`.
- `named_size_scale(target) -> dict[str, int]` (for Phase 5's capability brief).

- [ ] **Step 1: failing tests:**

```python
def test_pixel_target_gets_frame_and_cells():
    r = layout_flexible_page(Page.model_validate(SAMPLE), golden_target("pixoo64_3x5"), SAMPLE_CTX)
    assert r.frame.width == 64 and len(r.frame.pixels) == 64 * 64 * 3
    assert len(r.cell_lines) == 10 and "12:45" in r.cell_lines[0] + r.cell_lines[1]

def test_cell_target_has_no_frame():
    r = layout_flexible_page(Page.model_validate(SAMPLE), golden_target("flagship"), SAMPLE_CTX)
    assert r.frame is None and len(r.cell_lines) == 6

def test_issue_paths_start_at_blocks():
    r = layout_flexible_page(Page.model_validate(SAMPLE), golden_target("strip_32x8"), SAMPLE_CTX)
    assert all(i.path[0] in ("blocks", "layout", "style") for i in r.issues)
    assert any(i.code == "dropped" for i in r.issues)

def test_tiny_surface_reports_instead_of_crashing():
    t = FlexTarget(rows=0, cols=0, display=replace(profile("hub75_64x32"), width=4, height=4))
    r = layout_flexible_page(Page.model_validate(SAMPLE), t, SAMPLE_CTX)
    assert r.cell_lines == () and any(i.code == "surface_too_small" for i in r.issues)

def test_frame_is_deterministic_for_identical_inputs():
    a = layout_flexible_page(Page.model_validate(SAMPLE), golden_target("pixoo64_5x7"), SAMPLE_CTX)
    b = layout_flexible_page(Page.model_validate(SAMPLE), golden_target("pixoo64_5x7"), SAMPLE_CTX)
    assert a.frame.pixels == b.frame.pixels
```

- `SAMPLE` is a three-block page: a large centred time (priority 1), a wrapped weather line with `{sun}` and colour (priority 2), and a footer with a fill and priority 3. It lives in `tests/layout/devices.py` with a fixed `SAMPLE_CTX`.
- [ ] **Step 2: run** `$PYTEST tests/layout/test_engine.py -q`. Expected: `ImportError: layout_flexible_page`.
- [ ] **Step 3: implement** as specified.
- [ ] **Step 4: run** `$PYTEST tests/layout -q`.
- [ ] **Step 5: commit** `feat(layout): layout_flexible_page entry point`.

### Task 11: Golden fixtures for the spec's devices (parallel)

**Files:**

- Create `tests/layout/test_golden.py` and `tests/golden/layout/{pixoo64_3x5,pixoo64_5x7,strip_32x8,hub75_64x32,fiestapanel_led_192x96,max7219_32x8,flagship}.json`.

**Interfaces:**

- Consumes `layout_flexible_page` and `golden_target(name)`.
- Each golden holds:
  - `{"device", "frame_ascii": [rows] | null, "frame_sha256": str | null, "cell_lines": [...], "issues": [issue.to_json()...]}`;
  - plus an `rgb_spot` dict mapping `"x,y"` to `"#rrggbb"` for 3 chosen pixels on the rgb devices, so colour is held too.

- [ ] **Step 1: failing test:**

```python
@pytest.mark.parametrize("name", GOLDEN_DEVICES)
def test_flexible_layout_matches_golden(name):
    got = snapshot(layout_flexible_page(Page.model_validate(SAMPLE), golden_target(name), SAMPLE_CTX), name)
    path = GOLDEN / f"{name}.json"
    if os.environ.get("FIESTABOARD_UPDATE_LAYOUT_GOLDEN") == "1":
        path.write_text(json.dumps(got, indent=2) + "\n")
    assert got == json.loads(path.read_text()), "regenerate with FIESTABOARD_UPDATE_LAYOUT_GOLDEN=1 and review the ascii"
```

- [ ] **Step 2: run** `$PYTEST tests/layout/test_golden.py -q`. Expected: `FileNotFoundError` for each device.
- [ ] **Step 3: generate** with `FIESTABOARD_UPDATE_LAYOUT_GOLDEN=1 $PYTEST tests/layout/test_golden.py -q`. **Review every `frame_ascii` by eye** against the expectations, and note the review in the commit body:
  - the time is centred and is the largest text;
  - the strip shows only the time;
  - mono has no colour;
  - Flagship shows wrapped cells and a `size_ignored` issue.
- [ ] **Step 4: run** without the env var to confirm the files pass. Then break one rule (e.g. invert `valign` middle), confirm a golden fails, and restore.
- [ ] **Step 5: commit** `test(layout): golden flexible layouts for Pixoo, strip, HUB75, FiestaPanel, MAX7219 and Flagship`.

### Task 12: Fit rules for flexible pages (depends on Phase 0)

**Files:**

- Modify `src/pages/fit.py` (Phase 0's file) and `src/devices.py`: `pages_compatible_with_board` at 886.
- Test: `tests/layout/test_flexible_fit.py`.

**Interfaces:**

- Consumes `PageFit` and `page_fit_for_board`.
- Produces:
  - `page_fit_for_board(flexible_page, board)` returns `PageFit(True, None, None)`, unless `targets` excludes the board. In that case it returns `PageFit(False, None, "This page is set to show only on LED displays")` (or `"…only on the boards it lists"`).
  - `board_technology(board) -> str`: `display_profile_for_board(board).technology`, else `"split_flap"` for the Vestaboard and FiestaPanel outputs, else `"unknown"`.
  - `pages_compatible_with_board(page, board)` returns `page_fit_for_board(page, board).fits` for **every** flexible page, on any board, before Phase 0's LED delegation.

- [ ] **Step 1: failing tests:**

```python
def test_flexible_page_fits_split_flap_and_led_boards():
    assert page_fit_for_board(FLEX_PAGE, FLAGSHIP_BOARD) == PageFit(True, None, None)
    assert pages_compatible_with_board(FLEX_PAGE, PIXOO_BOARD)

def test_targets_technology_excludes_with_plain_reason():
    page = FLEX_PAGE.model_copy(update={"targets": FlexTargets(technology=["led_matrix"])})
    fit = page_fit_for_board(page, FLAGSHIP_BOARD)
    assert not fit.fits and fit.reason == "This page is set to show only on LED displays"
    assert not pages_compatible_with_board(page, FLAGSHIP_BOARD)

def test_targets_board_ids(): ...
def test_text_size_change_never_invalidates_a_flexible_page():
    for font in ("3x5", "5x7"):
        assert pages_compatible_with_board(FLEX_PAGE, {**PIXOO_BOARD, "output_config": {"font": font}})
```

- [ ] **Step 2: run** `$PYTEST tests/layout/test_flexible_fit.py -q`. Expected: `FlexiblePageGeometryError` raised from `pages_compatible_with_board`.
- [ ] **Step 3: implement** as specified.
- [ ] **Step 4: run** `$PYTEST tests/layout/test_flexible_fit.py tests/test_page_board_compatibility.py tests/test_schedules_service.py -q`.
- [ ] **Step 5: commit** `feat(pages): flexible pages fit every board unless targets excludes it`.

### Task 13: Render dispatch and full-frame delivery (depends on Phase 0)

**Files:**

- Modify `src/displays/service.py` (`DisplayResult`, line 30).
- Modify `src/pages/service.py`:
  - `page_plugin_ids` at 88;
  - `render_page` at 582;
  - `preview_page` at 827;
  - `preview_pages_batch` at 888;
  - `_board_key` at 672;
  - new `_render_flexible`.
- Test: `tests/layout/test_flexible_render.py`.

**Interfaces:**

- `DisplayResult.layout_issues: list[Any] = field(default_factory=list)`.
- `render_page(page, context=None, contexts=None, *, extended_markup=..., display=None, board: Mapping | None = None)`. The same `board=` keyword is added to `preview_page` and `preview_pages_batch`.
  - When `board` is `None`, a flexible page renders against the primary board (`_find_board(None)`), else flagship cells.
- `PageService._render_flexible(page, *, context, contexts, display, board) -> DisplayResult`:
  - target: `flex_target_for(board, display)`;
  - context: `shared_context_for(contexts, *geometry_of(board_or_default), plugin_ids=flexible_plugin_ids(page), display=display)`, else `engine.build_context(board_context_for(*geometry_of(board_or_default), display=display), plugin_ids=...)`;
  - layout: `layout_flexible_page`;
  - returns `DisplayResult(display_type="page:flexible", formatted="\n".join(cell_lines), raw={"page_id": page.id, "shown": [...]}, available=True, layers=[full_frame_layer(frame)] if frame else [], layout_issues=list(issues))`.
- `page_plugin_ids(page)` returns `flexible_plugin_ids(page)` for flexible pages.
- In `preview_pages_batch`, flexible pages key their shared context by the board's size key plus the display key.

- [ ] **Step 1: failing tests:**

```python
def test_flexible_render_on_pixel_board_carries_one_opaque_full_frame_layer(pixoo_board, pixoo_display):
    r = PageService(storage).render_page(FLEX_PAGE, context=CTX, display=pixoo_display, board=pixoo_board)
    assert r.available and len(r.layers) == 1
    layer = r.layers[0]; assert (layer.x, layer.y, layer.w, layer.h) == (0, 0, 64, 64)
    assert all(layer.rgba[i] == 255 for i in range(3, len(layer.rgba), 4))

def test_cells_under_the_frame_are_real_text_at_the_boards_grid(...):
    r = ...; assert len(r.formatted.split("\n")) == 10 and "12:45" in r.formatted

def test_flexible_render_on_flagship_is_cells_only(flagship_board):
    r = PageService(storage).render_page(FLEX_PAGE, context=CTX, board=flagship_board)
    assert r.layers == [] and len(r.formatted.split("\n")) == 6

def test_projected_rich_cells_carry_the_layer(pixoo_client, ...):
    chars, kw = project_for_output(pixoo_client, r.formatted, 10, 16, layers=r.layers)
    assert frame_layers(kw["cells"]) == tuple(r.layers)

def test_layout_issues_on_display_result(...): assert any(i.code == "dropped" for i in r.layout_issues)
def test_batch_preview_shares_context_by_board_size(...): ...  # one build_template_contexts_for key for 2 flexible pages
```

- The client fixture is the Pixoo output test driver used in `tests/canvas/test_page_send_layers.py`.
- [ ] **Step 2: run** `$PYTEST tests/layout/test_flexible_render.py -q`. Expected: the result is `available=False` with `Unknown page type: flexible`.
- [ ] **Step 3: implement.** Insert the flexible branch at the top of `render_page`, before the grid-geometry context lookup.
- [ ] **Step 4: run** `$PYTEST tests/layout/test_flexible_render.py tests/canvas -q`.
- [ ] **Step 5: commit** `feat(pages): render flexible pages to a full-frame layer over real cell text`.

### Task 14: Route every page geometry call site (depends on Phase 0)

**Files and routing.** Each site gets a behavioural test in `tests/layout/test_flexible_call_sites.py`, and its manifest entry in `tests/layout/geometry_call_sites.json` gets `kind: "page"` and the test id.

| Site | Routing |
|---|---|
| `src/main.py` send gate at 2464–2466 | Log with `page_size_label` |
| `src/main.py` send at 2538/2541 | `dims` and `device_type` come from the board (`board_dims_source`) for flexible pages. Pass `board=` to `preview_page`. If Phase 0 added a grid-for-delivery helper, use it. |
| `src/main.py` silence page at 2991–2997 and 3022 | Label helper; pass `board=` to the render |
| `src/pages/routes.py:265-266` | `page_size_key`; flexible pages skip `incompatible_references` |
| `src/pages/routes.py:690` and `src/settings/routes.py:746` | Use the primary board's dims for flexible pages; pass `board=` |
| `src/ops/executors.py` 469/576/618 sends and 561–562 | Same as the row above |
| `src/pages/routes.py:168-186` (`current-display`) | Flexible: `template` is the rendered cell lines; geometry from the primary board |
| `src/pages/service.py:360,369,386` (delete replacement) | When the deleted page is flexible: `369` accepts any page, and `386` creates a default flagship welcome page |
| `src/pages/service.py:1110-1129` | Label helper |
| `src/pages/service.py:_update_page_locked` | A geometry field in an update to a flexible page is a `ValueError("A flexible page has no grid; it fits every board")`, which becomes a 400 |
| `src/pages/service.py:669,679,955` | Covered by Task 13; flexible pages never reach them, asserted by a test |
| `src/pages/retarget.py:75` | Skip flexible pages |
| `src/panels/content_resize.py:88` | Flexible pages are kept by reference (no copy) |
| `src/ai/prompt_builder.py:511` | A flexible `current_page` uses the target board's geometry |

**Interfaces:** Consumes `page_size_key`, `page_size_label`, `is_flexible_page` (Task 3) and `render_page(board=)` (Task 13).

- [ ] **Step 1: failing tests.** One per site, named for the behaviour. Examples:

```python
def test_engine_sends_flexible_page_at_board_grid(engine_harness_pixoo):
    sent = engine_harness_pixoo.tick_with_active(FLEX_PAGE)
    assert sent.rows == 10 and sent.cols == 16 and len(frame_layers(sent.cells)) == 1

def test_retarget_skips_flexible_pages(...): assert all(m["page_id"] != flex.id for m in retarget_pages(...))
def test_put_device_type_on_flexible_page_is_400(client): assert client.put(f"/pages/{fid}", json={"device_type": "note"}).status_code == 400
def test_delete_last_flexible_page_creates_flagship_welcome(...): ...
def test_silence_page_may_be_flexible(...): ...
def test_current_display_for_flexible_page_returns_rendered_lines(client): ...
def test_panel_content_resize_keeps_flexible_page_reference(...): ...
def test_prompt_builder_with_flexible_current_page_uses_board_geometry(...): ...
```

- The engine harness is `tests/engine_harness.py`; mirror `tests/golden/engine/static_page_dedupe.json`'s setup.
- Remove the `xfail` from Task 3's manifest test.
- [ ] **Step 2: run** `$PYTEST tests/layout/test_flexible_call_sites.py tests/layout/test_geometry_call_sites.py -q`. Expected: `FlexiblePageGeometryError` at each unrouted site, and the strict xfail now unexpectedly passes or fails as designed.
- [ ] **Step 3: implement** the routings in the table.
- [ ] **Step 4: run** `$PYTEST tests/layout tests/test_page_retarget.py tests/test_silence_active_page.py tests/test_pages.py tests/test_panel_grid_pages.py -q`.
- [ ] **Step 5: commit** `fix(pages): route every page geometry call site for flexible pages`.

### Task 15: Render fingerprint and dedupe (depends on Phase 0)

**Files:**

- Modify `src/main.py`: `_render_fingerprint` at 1794 and its call at 2385.
- Test: `tests/layout/test_flexible_dedupe.py`.

**Interfaces:** `_render_fingerprint(page, active_page_id, page_service, contexts, *, override_active, display=None, board: Mapping | None = None)`. For flexible pages:

- it accepts `type in ("template","flexible")`, and requires `blocks` for flexible pages;
- the size comes from `size_key(*geometry_of(board))` plus `display.key`;
- the payload adds `"board_grid": [rows, cols]`;
- refs come from `page_plugin_ids` (already flexible-aware).
`content_key()` already digests `layers`, so the frame bytes are in the dedupe key.

- [ ] **Step 1: failing tests**, including **[RF-5]**:

```python
def test_flexible_page_gets_a_fingerprint(): assert DisplayService._render_fingerprint(FLEX_PAGE, "p", svc, {}, override_active=False, display=PIX, board=PIXOO_BOARD)
def test_identical_inputs_identical_content_key():                       # [RF-5]
    a, b = render(FLEX_CLOCK, "12:45"), render(FLEX_CLOCK, "12:45"); assert a.content_key() == b.content_key()
def test_minute_change_changes_content_key(): assert render(FLEX_CLOCK, "12:45").content_key() != render(FLEX_CLOCK, "12:46").content_key()
def test_fingerprint_differs_by_display_key_at_same_grid():
    f1 = fp(display=profile("divoom_pixoo64", font="3x5")); f2 = fp(display=replace(profile("divoom_pixoo64", font="3x5"), color="mono"))
    assert f1 != f2
def test_unchanged_tick_short_circuits_for_flexible_page(engine_harness_pixoo): ...  # second tick: no render call
```

- [ ] **Step 2: run** `$PYTEST tests/layout/test_flexible_dedupe.py -q`. Expected failure: the fingerprint is `None` for flexible pages.
- [ ] **Step 3: implement** as specified.
- [ ] **Step 4: run** `$PYTEST tests/layout/test_flexible_dedupe.py tests/test_render_short_circuit*.py tests/test_demand_driven_fetch.py -q`. Locate the short-circuit tests with `grep -l _render_fingerprint tests/*.py`.
- [ ] **Step 5: commit** `feat(engine): render fingerprint and dedupe cover flexible pages`.

### Task 16: `layout_issues` on previews and an unsaved flexible render route (depends on Task 13)

**Files:**

- Modify `src/pages/models.py`: `PagePreviewResponse` at 500, `PagePreviewBatchSuccess` at 510, `PageSendResponse` at 603.
- Modify `src/pages/routes.py`: 393, 444 and the new route.
- Update `tests/golden/responses/pages.json` and the route inventory golden (`tests/test_route_inventory.py`).
- Test: `tests/layout/test_flexible_preview_api.py`.

**Interfaces:**

- `layout_issues: list[LayoutIssueModel] | None = None` on all three responses. It is present only for flexible pages; grid responses are unchanged under `response_model_exclude_unset`.
- `PagePreviewBatchSuccess.layers` is set for flexible pages on pixel boards.
- `POST /pages/preview/flexible` takes body `{page: PageCreate (type flexible), board_id: str | None}` and returns `PagePreviewBatchSuccess` (`page_id: "unsaved"`). Phase 4's editor consumes it.

- [ ] **Step 1: failing tests:**

```python
def test_batch_preview_returns_frame_layer_cells_and_issues(client, pixoo_board_id, flex_id):
    body = client.post("/pages/preview/batch", json={"page_ids": [flex_id], "board_id": pixoo_board_id}).json()
    p = body["previews"][flex_id]
    assert p["layers"][0]["width"] == 64 and p["cells"] and isinstance(p["layout_issues"], list)
    assert all(isinstance(i["path"], list) and i["code"] for i in p["layout_issues"])

def test_grid_page_preview_has_no_layout_issues_key(client, grid_id): assert "layout_issues" not in client.post(f"/pages/{grid_id}/preview").json()
def test_unsaved_flexible_preview_renders_without_saving(client, pixoo_board_id): ...
def test_unsaved_preview_rejects_grid_page_422(client): ...
```

- [ ] **Step 2: run** `$PYTEST tests/layout/test_flexible_preview_api.py -q`. Expected failures: a missing key, and a 404 for the new route.
- [ ] **Step 3: implement.** `issues_json`-style helper: `layout_issues_json(issues) -> list[dict]`. Regenerate the response-shape golden with that test's documented `REGENERATE_HINT`, and review the diff: it must be additive only.
- [ ] **Step 4: run** `$PYTEST tests/layout/test_flexible_preview_api.py tests/test_response_shape_goldens.py tests/test_route_inventory.py tests/test_api_conventions_ratchet.py -q`.
- [ ] **Step 5: commit** `feat(pages): layout_issues on previews; unsaved flexible preview route`.

### Task 17: API and `/v1` acceptance, docs, web type tolerance (depends on Tasks 1, 13 and 16)

**Files:**

- Test: `tests/layout/test_flexible_v1.py`.
- Modify `docs/reference/api-endpoints.md` (the published API change note: `type: "flexible"` pages have no `template`; new preview fields; `document_protocol` `page-document-v2`).
- Modify `web/src/lib/api/shared.ts:11`: add `"flexible"` to `PageType`.
- Update any OpenAPI snapshot tests the schema change trips (`tests/test_api_docs.py`, `tests/test_openapi_front_page.py`).

**Interfaces:** `/v1/pages` reuses `Page`/`PageCreate`/`PageUpdate`, so acceptance needs no new code. These tests pin it.

- [ ] **Step 1: failing tests:**

```python
def test_v1_create_and_read_flexible_page(client):
    r = client.post("/v1/pages", json=FLEX); assert r.status_code in (200, 201)
    got = client.get(f"/v1/pages/{r.json()['id']}").json()
    assert got["type"] == "flexible" and "template" not in got and got["document_protocol"] == "page-document-v2"

def test_v1_list_includes_flexible_without_template(client): ...
def test_v1_update_replaces_blocks(client): ...
def test_v1_schedule_flexible_page_on_flagship_board_is_allowed(client): ...   # check_ref_board_compatibility
def test_import_flexible_share_string_round_trips(client): ...
```

- [ ] **Step 2: run** `$PYTEST tests/layout/test_flexible_v1.py -q`. Any failure here exposes a missed routing; fix it in its owning module.
- [ ] **Step 3: implement** any fixes, the docs and the one-line web type. Run the web tests in Docker per `CLAUDE.md`: `docker compose -f docker-compose.dev.yml --profile test run --rm web sh -c "npm ci --legacy-peer-deps && npm test"`.
- [ ] **Step 4: run** `$PYTEST tests/layout tests/test_pages_contract.py tests/test_api_docs.py -q`.
- [ ] **Step 5: commit** `feat(api): /v1 accepts and returns flexible pages; document the change`.

### Task 18: Transition fallback for full-frame deliveries (depends on Phase 0)

**Files:**

- Modify `src/settings/service.py`: `page_transition` at 121, only if Phase 0 did not already add a full-frame fallback.
- Test: `tests/layout/test_flexible_transition.py`.

**Interfaces:**

- Consumes Phase 0's fallback if present.
- Otherwise produces `page_transition(display, page, runs=None, *, full_frame: bool = False)`. With `full_frame=True`, a per-cell strategy (`flip`, `cascade`, the `column`/`row`/… flap strategies) or a `plugin:` strategy becomes `fade`.
- On split-flap boards, flexible pages produce plain grids, so every transition keeps working.

- [ ] **Step 1: failing tests:** `flip` and `plugin:typewriter` on a pixel board with a flexible page resolve to `fade`; on a Flagship the strategy is unchanged.
- [ ] **Step 2: run** to see the failure.
- [ ] **Step 3: implement**, or delete this task's code change if Phase 0 already covers it and keep only the tests.
- [ ] **Step 4: run** `$PYTEST tests/layout/test_flexible_transition.py tests/test_transition*.py -q`.
- [ ] **Step 5: commit** `feat(transitions): flexible pages on pixel boards fall back to fade`.

**Split-flap decision (the cheapest correct option).** Phase 1 renders flexible pages on split-flap and integer-only boards with the Task 9 cell layout. This includes FiestaPanel's LED viewer (`markup_follows_charset=False`), whose `_integer_authoring_profile` has no pixels. Nothing is excluded by fit. Phase 2 adds tile colour mapping for backgrounds and tiles, split-flap goldens beyond Flagship, and polish. The cell layout function is shared, not rebuilt.

### Self-review against the spec

| Spec section | Where it is met | Gap or deferral |
|---|---|---|
| §1 Two kinds of page; fits every board | Tasks 1, 12 | none |
| §2 Document: blocks, `priority`, `if`, `targets`, unknown kinds and properties preserved | Task 1 (generic `Block`, `ExtensibleDocument`); Task 6 (`if` via the canvas evaluator's `evaluate_expression`) | none |
| §3 Cascade device → board → page → block; v1 properties; colour, case and size rules | Task 5; the board level is the `board_style_for()` hook returning `{}` | Tile nearest-colour for backgrounds is Phase 2: it is reported as `background_dropped` now. Board-style storage is Phase 3. |
| §4 Fonts as families; one `fiesta` family; integer scaling; `kind` | Task 4; vendored files and hashes untouched | none |
| §5 steps 1–7: expansion (not `render_lines`), fill markers, measure, fit, stack, emit, report | Tasks 6, 7, 8, 9, 10; the stack is `(blocks, styles, rect)` over an arbitrary rect, tested for clipping | Breaking inside variables is not special-cased (breaks are at glyph boundaries; there is no kerning). Recorded here as the builder's call. |
| §6 Full-frame layer delivery; real cells under the frame; dedupe | Tasks 13, 15 | `output_api` 2 is out of scope. Per-output verification of the Pixoo, Ulanzi and FiestaPanel viewer is done by the Task 13/14 driver tests; the FiestaPanel viewer takes the cells path. |
| §6 Transitions fall back to fade | Task 18 (conditional on Phase 0) | Showing the fallback in board settings and the picker is UI (Phase 3/4). |
| §7 Fit; `targets`; size change never invalidates; no floor in the flexible path | Tasks 12, 14; constraint in Global Constraints | none |
| §8 Previews return frame, cells and `layout_issues` | Tasks 13, 16 (including the unsaved-page route) | The editor is Phase 4. |
| §11 Schema v7 no-op migration; `/v1` additive; share string; `document_protocol` v2 | Tasks 1, 2, 17 | none |
| Room for positioning: no stored positions; stack over a rect; issues carry paths | Tasks 1, 8, 5 | none |
| Constraint: every `geometry_of`/`size_key` call site routed and tested; `geometry_of` raises | Tasks 3, 14; the AST ratchet forces new sites to be classified | Direct `page.device_type` reads in MCP listings (`src/mcp_server.py` 1578/1711/1835/3357) still show `flagship` for flexible pages. These are Fiestabot surfaces and are flagged for Phase 5. |
| Constraint: Pi budget; cache faces and runs | Task 4 (`lru_cache` on scaled rows); Task 15 short-circuit | Add a perf smoke test if the reviewers want one. |
| Anti-goal: no third LED layout | Only `draw_glyph`/`paint_ops` and canvas raster are used; layout is Python-only | none |
| Left to the builder | Module `src/layout/`; one full-frame layer; share v2 for flexible only; named-size table in Task 4; default overflow `wrap`, valign `top`, gap `small`; unset priority drops first | Persisting `layout_issues` per board for board status is not built in Phase 1: they are returned on previews and `DisplayResult` only. Suggest Phase 3 store them on the board runtime. |

### Critical Files for Implementation

- /Users/jeffre/workspace/FiestaBoard/.claude/worktrees/flexible-pages-design/src/pages/models.py
- /Users/jeffre/workspace/FiestaBoard/.claude/worktrees/flexible-pages-design/src/pages/service.py
- /Users/jeffre/workspace/FiestaBoard/.claude/worktrees/flexible-pages-design/src/devices.py
- /Users/jeffre/workspace/FiestaBoard/.claude/worktrees/flexible-pages-design/src/led/matrix.py
- /Users/jeffre/workspace/FiestaBoard/.claude/worktrees/flexible-pages-design/src/main.py
