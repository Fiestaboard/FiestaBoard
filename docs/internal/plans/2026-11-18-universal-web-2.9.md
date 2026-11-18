# Universal web 2.9: complex editing (Figma 04b)

Slice 2.9 of the universal redesign (MASTER-PLAN Phase 2). It builds the
04b desktop expansions of the page editor on top of slice 2.5 and FiestaUI
`8.17.0-alpha.3` (the 1.11 components), plus hub H4 real-width validation.

## Scope

| Figma                                     | What ships                                                                                                                                                                                                                                                                                                                               |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 04b `126:134198` Lobby TV 96 × 24         | `ZoomControl` (Fit · Tile sm · md · lg, minimap toggle) in the preview header; `ColumnRuler` with the CUT mark that follows the preview scroll; `BoardMinimap` that pans the preview; `TruncationMap` from rendered rows and H4 verdicts, whose rows move the caret; `GoToCell`; `RowBand` gutter with Move up, Move down and Duplicate. |
| 04b `127:133562` Note array 2 × 2         | `NoteFocus` (All notes, Note 1–n) that scrolls the preview and outlines the Note with `NoteSeams`; a seam `ColumnRuler` above the template; a client-side seam-straddle check.                                                                                                                                                           |
| 04b `135:138801` Desk Pixoo canvas        | `ToolRail` for the pixel pad (brush, eraser, fill, eyedropper) with Undo and Redo; `LayersPanel` / `LayerRow` for the active canvas's shapes, reorderable.                                                                                                                                                                               |
| 07c `310:68695`, `310:71145`, `310:72331` | The docked preview's scroll states ("Column 1 of 2", "Columns 1–21 of 29") come from the kit `BoardViewport` that 2.4 and 2.5 already use; covered by the layout spec.                                                                                                                                                                   |
| 07c `307:41698`, `307:44268` (H4)         | One `EditorWarning` line-overflow card per line `POST /templates/validate` measures past the board's real width, with a Wrap action; touch-sized below 768 px.                                                                                                                                                                           |

The lenses are editor state only. No page model, hub route or schema changes.

## Design

- `web/src/lib/complex-editing.ts`: pure model (big-board test, bands,
  move and duplicate, H4 overflow parsing, truncation rows, seam marks and
  straddles).
- `web/src/lib/complex-editing-dom.ts`: caret placement in the rich and
  plain editors, and per-line boxes for the band gutter.
- `web/src/hooks/use-board-viewport-scroll.ts`: measures and drives the kit
  `BoardViewport` through its published `data-slot` parts and the tiles'
  `data-row` / `data-col`.
- `web/src/hooks/use-line-overflow.ts` and
  `web/src/lib/api/template-validation.ts`: H4.
- `web/src/components/complex-editing/`: the composed kit components and the
  canvas layers and history.
- `page-builder.tsx`: additive mounts only. The loading skeleton return moved
  below the new hooks so every render calls the same hooks.

The lenses switch on at the desktop pane (1024 px and up) for split-flap
previews: big boards (more than 44 columns or 12 rows) and note arrays with
more than one Note. Row bands also need 1280 px for the gutter.

## Tests

- Unit: `complex-editing-lib`, `complex-editing-dom`, `complex-editing-tools`,
  `complex-editing-canvas`, `complex-editing-overflow`,
  `page-builder-complex-editing`.
- Layout: `web/tests/layout/complex-editing.spec.ts` at 390, 900 and 1440 in
  light and dark, with axe.

## Deltas

Recorded as DD-W rows in the program's `DESIGN-DELTAS.md` and in
`status/web-2.9.md`.
