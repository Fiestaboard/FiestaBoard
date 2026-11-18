# Web slice 2.11 — Creator IDE (Figma 04d)

MASTER-PLAN Phase 2 row 2.11: Inspector tabs, Shows on, Problems; History and drafts.
Depends on FiestaUI 1.11 (`@fiestaboard/ui@8.17.0-alpha.3`) and hub H8, H9a/b/c (all in v11).

## Goal

At ≥1024 px the page editor becomes the 04d IDE (`184:159319`, region map `172:216366`):
Explorer · Editor · Preview + status row · Inspector tabs · docked console (Problems | Warnings | Sent) · week timeline.
Below 1024 px Problems becomes the Inspector's sixth tab and the week moves into Shows on
(Jev `desktop_console_two_option`, p=0.79).

## Integration (Jev `wrap_additive`, p=0.61)

The 3,459-line `PageBuilder` keeps its layout (2.9 and 2.10 edit it in parallel).

- `page-editor-shell.tsx` lazily loads `components/ide/creator-ide.tsx` for a saved page.
  It renders the Explorer into a slot beside the editor (portal) and the IDE dock under the
  editor, on the editor's own `[2fr 3fr]` grid so Console + Timeline sit under the template
  column and status row + Inspector sit under the preview column.
- Two additive `PageBuilder` seams: an optional `saveActions` render prop (replaces Save and
  Show now while a display shows the page: Save draft + Save & update board, 04d decision 4)
  and `isMirroring()` on the handle (the status row's Testing state).
- Jump to source moves the caret through TipTap's `dom.editor` (or the plain textarea), so no
  new editor handle is needed.

## Data (real hub only)

| Surface | Producer |
|---|---|
| Status row display state, Shows on "Now", "until" | H8 `GET /schedules/active/page` per display + schedule windows |
| Shows on collections | H8 `POST /collections/{id}/dry-run` (rule dry run at now) |
| Problems | H4 `POST /templates/validate` at the open display (board charset, page geometry) |
| Warnings | `POST /templates/render` `charset_issues` at the display (substitutions) |
| Sent | H9b `GET /pages/{id}/sends` → SentLog; failed/silenced as ProblemItems (kit gap) |
| Draft / Save draft / publish / discard | H9a `…/draft` routes |
| History, Compare, Restore | H9a `…/revisions`, restore → draft, 409 asks before `replace_draft` |
| Make a copy for another display | H9c `POST /pages/{id}/duplicate` + crop report |

## Edit state (C29), derived

Testing (mirroring) › Unsaved (edits neither the page nor the draft has) › Draft (hub draft) › Saved.

## Tests (TDD)

- `ide-lib.test.ts`: tab lists, data sources, edit state, jump to line, problems/warnings,
  sends mapping, revision diff regions, Shows on model, template references.
- `creator-ide.test.tsx`: compact vs desktop tabs and console, Explorer portal, H4 request,
  status message, header actions + Save draft body, draft discard after save, Page/Data/Logic
  tabs, Shows on Now + dry run, duplicate + crop report, restore 409 confirmation, compare.
- `messages-creator-ide.test.ts`: 14 locales, same keys and placeholders.
- `tests/layout/creator-ide.spec.ts`: 390 / 900 / 1440 × light/dark with axe (CI).

## Not built

- Rule tester ("which page wins at…", P12): design spike per the IDE rulings.
- Snippets: no producer on the hub; honest unavailable line.
- Tags facet (H9c tags): not drawn on web 04d.
