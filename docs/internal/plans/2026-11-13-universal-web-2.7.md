# Universal web slice 2.7: keyboard shortcuts (WEB-17)

**Goal:** `?` opens the kit's `ShortcutListPopover` (FiestaUI 1.4d, PR #395) in the page editor, the two triggers sit where Figma 07 `57:27771` draws them, and the list and the real key bindings read one registry so they cannot drift.

**Design source:** Figma `ZQ8RMELCO6qEOFZUnQu36e`, 07 `57:27771` (editor), `57:28953` (popover), `57:28576` (header "Shortcuts" button), `57:28704` (toolbar hint "? All shortcuts"); 08 `59:68086` (W4).

## Audit: the editor shortcuts that exist today

| Action                           | Keys               | Where it is bound                                                        |
| -------------------------------- | ------------------ | ------------------------------------------------------------------------ |
| Undo                             | Mod+Z              | `TipTapTemplateEditor` `handleKeyDown`; `page-builder` draw-mode handler |
| Redo                             | Mod+Shift+Z, Mod+Y | the same two handlers                                                    |
| Apply a formula (formula editor) | Mod+Enter          | `FormulaEditorPanel` CodeMirror keymap                                   |
| Close a picker                   | Esc                | `ToolbarDropdown`, `FormulaNodeView`                                     |
| Leave draw mode                  | Esc                | `page-builder` draw-mode handler                                         |

Not listed, because no binding exists in web today: 07's `/` insert menu, Mod+Shift+L/E/R alignment, Mod+S Save and Mod+Enter Show now. BoardViewport's ← → / Home / End / F (FiestaUI 1.5a, #387) are recorded in the registry as kit-owned keys, but listed only when the preview renders a BoardViewport (`boardViewport` option, which slice 2.4 turns on). Jev `jev_decide`: `gate_on_viewport`, p 0.91.

## Architecture

- `web/src/lib/editor-shortcuts.ts`: the registry (`EDITOR_SHORTCUTS`, chords in `Kbd` key names), `matchesShortcut(event, shortcut)`, `codeMirrorKey(shortcut)`, `isTypingTarget(target)`, and `editorShortcutGroups(t, { boardViewport })`.
- Every handler above calls `matchesShortcut` / `codeMirrorKey` with its registry entry instead of spelling its own keys.
- `web/src/components/editor-shortcut-list.tsx`: `useEditorShortcutList` holds one open state and binds `?` outside inputs, text areas, selects, contenteditable and other dialogs or menus; `EditorShortcutList` renders the header "Shortcuts" button or the "? All shortcuts" hint, each as a `ShortcutListPopover` anchored to the Template heading, so the list hangs in the template column (DD-W30).
- `page-builder.tsx`: mounts the two triggers (header, before Save; the row above the template, right-aligned) and passes the Template heading as the anchor.

## Tasks (test-first)

1. RED: `editor-shortcuts.test.ts` (matcher, CodeMirror key, typing guard, groups with and without BoardViewport). GREEN: the registry.
2. RED: `editor-shortcut-list.test.tsx` (`?` opens; ignored in input/textarea/contenteditable and with modifiers; both triggers open; Escape closes; rows come from the registry). GREEN: the component.
3. Route the existing handlers through the registry; existing page-builder, TipTap and formula tests stay green.
4. Mount in `page-builder.tsx`; messages in all 14 locales.
5. Playwright `tests/editor-shortcuts.spec.ts`: desktop open by `?`, by both triggers, guard in the name input, axe on the open list; touch context (`hasTouch`, no fine pointer) asserting the triggers are hidden and `?` still opens the list on screen.
6. Typecheck, lint, format, build, `test:coverage`; screenshots at 390 / 768 / 1280, light and dark.

## Review round 1 (Opus, `reviews/pr-2478-review.md`)

- M1: the formula modal is a real modal dialog (`role="dialog"`, `aria-modal`, a name). The `?` hook skips while any `aria-modal` element or `data-editor-overlay` panel is open. ToolbarDropdown panels are named dialogs carrying that marker.
- M2: the formula Done button renders `ShortcutKeys` (kit `Kbd`) from `EDITOR_SHORTCUTS.applyFormula`, with `aria-keyshortcuts`.
- M3: "? All shortcuts" moves into the template toolbar's new `trailing` slot. Plain text and the LED editor keep it above the Template heading (DD-W59).
- S1: `editor-shortcut-bindings.test.tsx` requires a binding test for every listed row.
- S2: no anchor while the template column is hidden; `boardViewport` comes from `previewBindsBoardViewportKeys`.
- S4: the undo and redo tooltips render their chords from the registry.

## Re-review follow-up (RR-M1)

1. Add Playwright regressions at 768 and 1024: one hint above the toolbar; at 768 it shares the preview-toggle row. Resizing to 1280 moves it into the toolbar.
2. Finish the inherited media-query hook and gate both placements at xl (1280), because the review measures a wrap at 1024 too. Preserve one hint per layout.
3. Isolate FormulaNodeView's Esc/deletion test from its lazy CodeMirror panel; keep real panel keymap and Done coverage in the existing suite.
4. Pin registry alpha.1 and verify the lockfile, full coverage suite, typecheck, lint, format, build and sequential one-worker editor/a11y e2e. Capture 390/768/1024/1280 light/dark screenshots.
5. Record the kit trailing-slot gap, DD-W59's responsive fallback, and the shared 2.4 flag handoff; push normally and observe CI.

Jev `jev_decide` selected `responsive` (p 0.50, confidence 0.37) over accepting the tablet wrap (p 0.36). The measured 1024 wrap requires a wider boundary than the inherited lg-only change; browser regressions verify this choice.
