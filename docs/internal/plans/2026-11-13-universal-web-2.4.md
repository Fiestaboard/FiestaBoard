# Web 2.4: boards scroll horizontally; Actual size is the default (WEB-07)

**Goal.** Every readable board preview in the web app keeps its real tiles and
scrolls inside its bezel instead of shrinking (owner rule 9). It uses the
FiestaUI `BoardViewport` (1.5a, FiestaUI #387): edge fade, snap, "Note 1 of 3",
← → / Home / End / F, and a labelled Fit overview below `minTile` 13.

**Figma:** 02 `36:35275`, `52:122709`–`52:123502`; 07 `57:27771`; 07c `310:68695`.

## Approach (Jev `jev_decide`, p = 0.91: "choke point")

The app already funnels its boards through one wrapper,
`src/components/scaled-board-display.tsx`. Converting that wrapper converts every
call site at once, including the files other slices hold (2.2 `active-page-display.tsx`
and `compose-page-dialog.tsx`, 2.7 `page-builder.tsx`), with no edits to them.

1. New `src/components/board-viewport.tsx`: the app's `BoardViewport`. It wires
   the same chrome as `BoardDisplay` (`useBoardChrome`: animation gate, flap speed,
   translated names) and localises every `labels.*` string and the hint.
   - Hint: the 07 keyboard hint on a fine pointer ("Shift + scroll, trackpad swipe,
     or ← → when focused. Snaps to each Note." / "… each column."); 02's "swipe"
     on a coarse pointer.
2. `src/components/scaled-board-display.tsx` renders the app `BoardViewport` by
   default. A new `thumbnail` prop keeps the FiestaUI `ScaledBoardDisplay` fit path,
   with `mode="fit"` and `persist={false}`, so a session's "Actual" choice never
   turns a thumbnail into a scroller.
3. Thumbnail call sites pass `thumbnail`:
   - `page-grid-selector.tsx` `PageButtonPreview`: the board sits inside the page
     `<button>`. A scroll region or toggle there would be a nested-interactive
     control (axe).
   - `collection-page-stack.tsx`: a decorative, `inert`, `aria-hidden` stack.
4. `displays/display-live-preview.tsx` names each board's region after its display
   ("Kitchen preview"), as the #387 docs ask for lists.
5. Persistence follows the kit: one session key (`fiestaboard:boardPreviewMode`).
   A Fit tap lasts the session and carries to boards mounted later. Thumbnails
   never read or write it.

## Call-site inventory

| Call site                                                                                          | Result                                                                                                           |
| -------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Home hero `active-page-display.tsx`                                                                | BoardViewport (through the wrapper)                                                                              |
| Editor preview `page-builder.tsx`                                                                  | BoardViewport (through the wrapper); draw mode hit-tests tiles inside the scroller                               |
| Compose dialog `compose-page-dialog.tsx`                                                           | BoardViewport (through the wrapper)                                                                              |
| Display detail and Displays list `display-live-preview.tsx`                                        | BoardViewport, with a per-display region name                                                                    |
| Setup wizard `wizard/step-board-setup.tsx`                                                         | BoardViewport (through the wrapper)                                                                              |
| FiestaBot inline preview `inline-board-preview.tsx`                                                | BoardViewport (through the wrapper)                                                                              |
| Page grid card `page-grid-selector.tsx` `PageButtonPreview`                                        | `thumbnail` (inside a button)                                                                                    |
| Page grid cascade `page-grid-selector.tsx` `StaticBoardDisplay`                                    | unchanged: a bleeding decorative cascade                                                                         |
| Collections stack `collection-page-stack.tsx`                                                      | `thumbnail` (inert, decorative)                                                                                  |
| Settings flap-speed demo `settings/animation-settings.tsx`                                         | unchanged: a 15-column Note at Tile sm (~244 px) always fits                                                     |
| FiestaPanel TV surface `panel/panel-board.tsx`                                                     | unchanged: it is the display itself, scaled to fill the TV, not a preview                                        |
| LED boards (`DevicePreview` → `DisplayPreview`, `panel-tv-preview`, `panel-matrix-editor-preview`) | unchanged: LED matrices are drawn by `DisplayPreview`; BoardViewport only draws split-flap boards (FiestaUI gap) |

## Tests (written first)

- vitest `src/__tests__/board-viewport.test.tsx`: localised labels, the hint per
  paging kind and pointer, region name override, the chrome passthrough.
- vitest `src/__tests__/scaled-board-display.test.tsx` (rewritten): the wrapper
  renders BoardViewport by default with Actual size as the default for every board
  type; `thumbnail` stays fit, ignores a stored "actual", and never writes the key.
- Layout (real Chromium, no backend) `tests/layout/board-viewport.spec.ts`:
  a Flagship and a 3×1 array at 390 / 768 / 1280; scroll, snap, keys, F, the
  overview label, edge fades, thumbnail fit, axe.
- E2E `tests/board-viewport.spec.ts`: Home at 390 scrolls the board, F gives the
  overview, the mode lasts a reload in the session; axe on the state.
- New files join the coverage threshold list.

## Review completion ledger (Codex handoff)

- Preserve and verify the incoming uncommitted M1/M2/S1–S5 fixes.
- M1: build FiestaUI origin/alpha plus 1.5d in an isolated scratch clone;
  install with `--no-save`, keep thumbnails fitted with no controls, prove
  note-array thumbnails are clean inside a card button with axe.
- M2: use columns × rows for the four remaining dimension strings in every
  locale and update wizard / geometry assertions.
- S1/S2: test chrome translation and animation settings, per-display names,
  page-card thumbnails and decorative collection-stack thumbnails.
- S3: name FiestaBot previews by reply and tool step; exercise real preview
  accessible names in the transcript tests.
- S4/S5: reconcile DD-W26 and status to 1–16 at 390 / 1–21 at 768;
  preserve 1.5e's phone-hero gate and hand Home's stale comment to 2.2.
- Verify the shared coarse-pointer hook against 2.6 without editing it.
- Run static checks, full coverage, layout, relevant e2e (one spec at a time,
  one worker), and refresh screenshots with a touch context at 390.
- Commit with the repository trailer, push normally, update only this PR's
  body, observe CI, and record the exact results in the program status.

Ruling: keep the current registry pin while 1.5d remains unpublished; remain
in draft, with publication plus a new registry pin and rerun required before
ready. Jev selected this handoff at p = 0.75 (alpha.1-only pin 0.17).
An alpha.1 bump alone cannot supply `showModeToggle`; no tarball is committed.
