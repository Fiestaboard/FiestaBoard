# Pencil Draw Mode — Design

**Date:** 2026-07-22
**Status:** Approved (user), executing

## Summary

Add a pencil tool to the rich (TipTap) template editor toolbar. When active, the
board preview below the editor becomes a paintable surface: the user picks a
brush from the toolbar — one of 8 inline color swatches, an eraser button, or a
stamp character from a character dropdown — and clicks or drags across board
tiles to paint them. Typing characters remains the primary text path via the
rich editor itself; the character brush is for stamping individual tiles.

## Decisions (from brainstorming)

- **Location:** pencil toggle lives in the existing TipTap toolbar in
  `PageBuilder`'s rich mode. No third editor mode, no new route.
- **Tools:** pencil (click + drag painting) with 8 inline color swatches on the
  toolbar, a dedicated eraser icon button, and a character dropdown for
  stamping A–Z / digits / punctuation onto tiles. No fill-all. *(Superseded:
  the first iteration used a color dropdown attached to the pencil and had no
  character stamping; user feedback moved the swatches inline and brought
  character stamping in scope — typing in the RCE remains the primary text
  path.)*
- **Toolbar transform:** while the pencil is active, the RCE text content area
  is collapsed (toolbar remains visible) so it is obvious the board preview is
  the editing surface, and the toolbar **transforms** into
  `[pencil active] | [undo/redo] | [8 color swatches] [eraser] | [character dropdown]`.
  All content-editing controls (cut/copy/paste, variable/color/formatting
  inserts, formula, wrap, alignment, sync-from-board) are hidden — not
  rendered — while drawing; undo/redo stay. Exiting restores the normal
  toolbar. *(Supersedes the first-iteration decision to keep the full toolbar
  visible with content buttons disabled; user feedback was that the disabled
  buttons were clutter.)*
- **Variables:** painting is positional, variables are dynamic. Painting any
  cell of a line that contains `{variable}` tokens strips those tokens from the
  line (it does NOT freeze rendered values into static text). The removal is
  undoable.
- **Undo/redo:** full stack via ProseMirror history — paints are applied as
  TipTap document transactions, so Cmd/Ctrl+Z / Shift+Z and the toolbar
  undo/redo buttons work naturally. One drag stroke = one undo step.
  **Known limitation:** undo restores line *content* (including any
  `{variable}` tokens stripped by normalization), but the `alignment: "left"` /
  `wrap: "off"` metadata forced onto a line the first time it is painted is
  NOT restored by undo — that metadata lives in `PageBuilder`'s React state
  (`lineAlignments` / `lineWrapEnabled`), outside ProseMirror's document and
  therefore outside its history stack. Undoing a paint can leave a line back
  at its original (pre-paint) text with alignment/wrap still forced from the
  paint. Full metadata restore (e.g. snapshotting and rolling back alignment/
  wrap alongside the document transaction) is a known follow-up, not covered
  by this design.
- **Exit:** Esc or clicking the pencil toggle again exits draw mode and
  restores the text area.

## Architecture

### Source of truth

The template stays the single source of truth. No new page schema, no backend
changes, no migrations. Painting cell `(row, col)` rewrites template line `row`
so that cell position `col` is a color tile (`{{red}}` etc.) or a blank
(eraser). A painted page is an ordinary page: save, preview, scheduling, live
output, and all device types (flagship 6×22, note 3×15, note arrays up to
24×120) work through the existing pipeline untouched.

### Positional normalization

A paintable line must be positional (cell N = template character N). On the
first paint touching a line, the line is normalized:

1. Strip `{variable}` tokens (anything in single braces that is not a color
   marker). Color markers and literal characters are kept.
2. Force that line's alignment to `left` and wrap to `off` (via the existing
   per-line metadata in `PageBuilder`).
3. Pad with spaces so the painted column exists.

Untouched lines keep their variables, alignment, and wrap settings.

### Cell model

A template line maps to board cells as: one literal character = one cell, one
color marker (`{{red}}` / `{63}`) = one cell. The paint utilities convert
line-string ⇄ cell array using the same tokenization rules as
`board-display.tsx`'s `parseLine` and the TipTap serialization
(`web/src/components/tiptap-template-editor/utils/serialization.ts`).

### Applying paints

Paints are applied to the TipTap document (`colorTile` atom node insertion /
text replacement at the computed doc position), not to `templateLines` state
directly. This keeps the RCE content in sync when re-expanded, and ProseMirror
history provides undo/redo. A drag stroke batches its cell writes into a single
transaction (or a single history group) so it is one undo step.

### Interactive preview

`BoardDisplay` gains an optional paint mode (new props: `paintable`,
`onPaintCell(row, col)` or similar; wired through `ScaledBoardDisplay`):

- While painting, the static tile path (`isStatic`) is used — no per-tile
  animation hooks, so even 2,880-tile note arrays carry zero per-cell state.
- One delegated pointer listener on the board container; no per-cell handlers.
  Cells are identified from the event target via `data-row`/`data-col`
  attributes (added to tile wrappers), so `ScaledBoardDisplay`'s CSS
  `transform: scale()` never enters coordinate math. Drag uses pointer capture
  + `document.elementFromPoint` to hit-test mid-stroke.
- Immediate feedback: painted lines are positional literals, so the client
  composes the preview message locally for painted lines (no waiting on the
  debounced server preview round-trip); unpainted lines continue to show the
  last server-rendered output.
- Per-row memoization: painting one cell re-renders one row, not the grid.

## Error handling

- Painting out of bounds is impossible (only rendered tiles are hit-testable).
- If a line cannot be normalized (unparseable content), the paint is a no-op
  and a console warning is logged — no crash, no data loss.
- Exiting draw mode never loses text content: the RCE is collapsed, not
  unmounted; its document is the source of truth throughout.

## Testing

- **Vitest unit tests** for the paint utilities: line⇄cells tokenization,
  positional normalization (variable stripping, padding), paint application,
  eraser, doc-position mapping.
- **Playwright e2e** (`web/tests/draw-mode.spec.ts`): activate pencil, pick a
  color swatch, click cells, drag a stroke, erase, stamp a character, paint
  over a variable and undo to restore it, editor collapse/restore, toolbar
  swap (content controls absent, swatches/eraser/char dropdown present), save the page,
  send to board and verify painted codes in the mock board grid
  (`getMockBoardState()` + helpers). Runs against flagship, note, and a
  note-array configuration.
- **Video proof** — a demo spec run with Playwright video recording enabled
  (scoped so the main suite stays video-off) that walks the full flow: open
  editor → pencil → draw a shape → erase → undo → save → send to board. The
  `.webm` is the deliverable.

## i18n & a11y

- New strings under a `drawMode` (or `tiptapEditor`) namespace in
  `web/messages/en.json` and all 14 locales: pencil tooltip, color names
  (reuse existing color keys where present), eraser, stamp-character dropdown
  label, drawing-mode hint.
- Pencil toggle exposes `aria-pressed`; tiles get `aria-label`s only in paint
  mode if cheap, otherwise the RCE remains the accessible editing path (the
  preview is `aria-hidden` decorative today).

## Out of scope

- ~~Character stamping on the preview (typing happens in the RCE).~~
  **Superseded:** character stamping is now IN scope via the toolbar's
  character dropdown (`DrawBrush = { kind: "char", char }`); typing in the RCE
  remains the primary text path.
- Fill-all / clear-all tools.
- New page content types or backend changes.
- Plain-text editor mode integration (pencil is rich-mode only).
