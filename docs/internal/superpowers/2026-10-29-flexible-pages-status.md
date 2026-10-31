# Flexible pages: parked status (2026-10-29)

**State: PARKED.** On 2026-10-29 the owner said: "Sit on this work. We should be doing this eventually, but right now maybe not." Nothing has been pushed, no PR has been opened, and the work hasn't been tested on a real device. Don't push, deploy or start new phases until the owner brings it back.

## What this is

FiestaBoard LED pages that don't depend on the display. Each page sets its own text size, font face and style, and there's room to add positioned "canvas-like" areas later.

- Design: `docs/internal/superpowers/specs/2026-10-28-flexible-pages-design.md`
- Plans: `docs/internal/superpowers/plans/2026-10-28-phase-0-grid-pages-own-size.md` and `...-phase-1-flexible-pages-core.md`

## Where the code is

| Branch (local only) | Worktree | Contents |
|---|---|---|
| `feat/flexible-pages` | `.claude/worktrees/flexible-pages` | **The real branch.** Phase 0 + Phase 1 + all review fixes. Head `6235e7438` before this note. |
| `feat/flexible-pages-core` | `.claude/worktrees/flexible-pages-core` | Phase 1 tasks 1–11 only. Already merged into the branch above, so it can be deleted. |
| `docs/flexible-pages-design` | `.claude/worktrees/flexible-pages-design` | Design and plans only (`ef5acfecc`). Also contained in the real branch. |

- **Branched from:** `main` at `ff2415c4a` (v10.1.20). `main` will move on, so expect to rebase. The most likely conflicts are in `src/devices.py`, `src/pages/service.py`, `src/main.py`, `src/mcp_server.py` and `src/outputs/`.
- **Backup bundle:** `~/workspace/FiestaBoard-parked/flexible-pages-2026-10-29.bundle`, holding all three branches. To restore: `git fetch <bundle> 'refs/heads/*:refs/heads/*'`.

## What's built

**Phase 0 (Divoom fix):**
- Grid pages on LED boards render at their own text size, as one full-frame layer with real cell text underneath.
- A page fits if its grid is any grid the board can produce.
- Pages a board can't show are flagged with a reason, not hidden.
- Changing a board's text size no longer moves pages. Board settings list the pages left behind instead.
- The editor previews and sends a page at its own size.
- Transitions fade around full-frame pages.

**Phase 1 (flexible pages core):**
- Page type `flexible` with `blocks`, `style`, `layout: {kind: "stack"}` and `targets`, in schema v7.
- Share strings use envelope v2.
- `src/layout/`: fonts, style cascade, expansion, measure/fit, stack, cell layout and the engine entry point `layout_flexible_page`. Golden tests are in `tests/golden/layout`.
- Fit, render dispatch, fingerprint and dedupe, previews (including unsaved previews and `layout_issues`), `/v1`, MCP and ops.
- Transitions fall back to fade.
- `geometry_of` refuses flexible pages. Ratchet tests catch geometry call sites, and direct page grid-field reads in MCP and ops, that ignore flexible pages.

## Verification at park time

- **Python:** full suite run from a clean `git archive` export: 15054 passed, 2 skipped, 1 failed. The failure is the git-only test `test_check_image_formats`, which needs `.git`.
- The worktree's ignored `data/` holds probe state that makes 9 settings and wire-golden tests fail. Clear it, or test from a clean export.
- **Web:** vitest 3105 passed, typecheck clean, eslint clean (with `npm ci --legacy-peer-deps` in `web/`).
- **Not done:** any run on a real device or on fiestapi.local.

## Review history

- Each task got its own reviewer.
- A Fable whole-branch review then ran 4 rounds: 3 blocking findings, then 1, then 1, then 0.
- A final follow-up fixed the last Important finding (a text block that fits to nothing is now reported as `dropped`, not lost silently) and two minors.

## Open follow-ups (none block merge)

- Section 7's output-capability clause in the spec: there's a TODO in `src/pages/fit.py`.
- Batch preview of face pages makes extra plugin fetches.
- The `_board_kw` rule is duplicated in `src/main.py` and `src/pages/board_render.py`.
- The web `editorCharset` needs a follow-up.
- On a secondary board, a forced refresh of a grid page in MCP `get_current_display` no longer writes to the shared preview cache. To keep the cache write, pass the board only for flexible pages.
- Phase 6 (converting grid pages to flexible pages) is deferred by design.

## To resume

1. Rebase `feat/flexible-pages` onto current `main` and re-run both suites.
2. Test safely first by running the branch in Docker on a Mac with a Divoom output.
3. Only then try fiestapi.local, and before that:
   - back up `/opt/fiestaboard/data`, since v7 pages may not load on released builds;
   - turn off auto-update;
   - load an arm64 image built from the branch.
4. Write the plans for phases 2–5: split-flap polish, board style settings, an editor with multi-board preview, and Fiestabot tools.
5. When the owner says go, open the PRs against `main`, not `next`.
