# Universal web slice 2.6: Collections reorder via SortableList (WEB-06)

**Date:** 2026-11-13
**Branch:** `feat/universal-web-2.6-collections-reorder`, based on `feat/universal-web-2.0-fiestaui-alpha` (#2471).
**FiestaUI:** `SortableList`, `SortableListHandle`, `SortableListMoveButtons`, `ListRow`, `ListRowGroup` (slices 1.8a/b, FiestaUI #389). Until `8.17.0-alpha.1` is on npm, the slice is developed against a local tarball of FiestaUI `alpha` + #389 (`ba1ea720`), installed with `npm install --no-save`. The committed pin stays `8.17.0-alpha.0`.

## Goal

Replace the HTML5 `draggable` page list in `collection-form.tsx` with the FiestaUI SortableList pattern (08 P7 `61:53985`):
pointer drag (mouse, pen and touch in one path), keyboard lift with Space, ↑ ↓ to move, Space to drop and Esc to cancel, Move up / Move down, and a polite live region that announces each step.
The saved order goes through the existing `PUT /v1/collections/{id}` `page_ids` field; no hub change.

## Design source (Figma `ZQ8RMELCO6qEOFZUnQu36e`)

- 07 `57:66920`: Mobile Safari 390, Collections · Weekday mornings · Dragging. 64 px cards (radius 12), 44 px grip, title, meta, ••• menu; the lifted card has a 2 px amber stroke; an insertion line with a dot; status line "Morning commute · moving to position 1 of 4". Hint: "Drag the handle, or use ··· › Move up / Move down."
- 07c `312:74870`: desktop keyboard reorder. Card rows with grip, index number, title + meta, Move up / Move down on the lifted row, ••• menu; status line; Kbd legend "Space lift / drop · ↑ ↓ move · Esc cancel".
- 07c `316:98955`: tablet time-based (numbers shown, lifted ring).
- 07c `312:76483`: Random selection. One inset group, plain rows (title, meta, × remove), no handles: "Order doesn't matter, so there are no handles."
- 08 `61:25752` (C16 ListRow) and `61:53985` (P7 SortableList).

## Changes

1. **`collection-page-list.tsx` (new).** Presentational list for the form.
   - Time mode: `SortableList` of `ListRow variant="card"` with `leading` = `SortableListHandle` + position number (≥ md), `description` = the page's shape (Flagship, Note, Note Array 2×2, Panel 12×29), `trailing` = `SortableListMoveButtons` (≥ md, as 07c) + a ••• `DropdownMenu` with Move up, Move down and Remove.
   - `size="touch"` on a coarse pointer (`useCoarsePointer`, new hook), giving the 44 px handle and 56 px rows of 07.
   - All SortableList copy comes from i18n (`collections.sort*`).
   - Random and variable modes: `ListRowGroup variant="inset"` with one plain `ListRow` per page and an × remove button (07c `312:76483`).
2. **`collection-form.tsx`.** Drops `dragIndex`, the HTML5 page drag handlers, `movePage` and the hand-made row markup; renders `CollectionPageList` with `onMove = arrayMove`. Variable-rule reorder is unchanged (not WEB-06).
3. **i18n.** New `collections.*` keys in all 14 locales (leaf-key parity test); `movePageUp` / `movePageDown` removed (unused); `dragToReorder` copy updated to the 07c hint, plus `dragToReorderTouch` for the 07 hint below md.
4. **Hub.** No code change. `tests/test_v1_contract.py` gains a round-trip test that a PUT with a reordered `page_ids` is stored and returned in that order (the existing contract only covered create).

## Tests (test-first)

- `src/__tests__/collection-page-list.test.tsx` (new): keyboard lift/move/drop calls `onMove` and announces; Esc restores; Move up / Move down; pointer drag on the handle reorders once on drop; menu items move and remove; random mode has no handles and keeps × remove; shape descriptions; coarse pointer gives `size="touch"`.
- `src/__tests__/collection-library.test.tsx`: the keyboard reorder test now lifts with Space and saves the new `page_ids`.
- `src/__tests__/use-coarse-pointer.test.ts` (new).
- `web/tests/collections-reorder.spec.ts` (new Playwright): reorder by keyboard, save, reload, assert order; reorder by pointer drag, save, reload, assert order; axe on the editor.
- Coverage list in `vitest.config.ts` gains the two new source files.

## Out of scope (recorded as deltas / follow-ups)

- Per-page duration selects (07c rows) — the hub has one interval per collection.
- Board name in row meta ("Kitchen board · Flagship") — pages are not bound to a board.
- The page header, Now in this Collection pane, Show now, selection-mode chips and "+ Add page" button of 07c.
- Variable-rule reorder (still HTML5 drag in `variable-rule-row.tsx`).
- `DropdownMenu trigger="context"` on sortable rows (Jev `jev_decide`: menu_only, p = 0.99).
