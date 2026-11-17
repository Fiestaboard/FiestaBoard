# Editor touch pass implementation plan

> For agentic workers: use superpowers:executing-plans for application work; independent agents own e2e and locale files. User preauthorizes autonomous execution and final Astra review.

Goal: always-visible kit preview, touch editing and complete Save / Show now flows.
Architecture: retain split-flap TipTap engine and live-render pipeline; adopt FiestaUI EditorPreview and toolbar/picker primitives. Charset editor retains its kit engine. Shared controlled BoardViewport mode persists session preference.
Tech stack: React Router, React Query, FiestaUI 8.17.0-alpha.2, Vitest/MSW, Playwright/axe.
Spec: program/briefs/WEB-SLICE-BRIEF.md, WEB-BATCH3-RULINGS.md and shots/web-2.5/FIGMA-REFS.md in external program hub.

## Global constraints
- Sheets below 640 px; dock below 1024 px; touch toolbar below 768 px or coarse pointer.
- Mirror switch ships together with dock; off on each editor open; reuse existing live requests/target pinning.
- Kit components only; record any unavailable API as FiestaUI follow-up and compose existing kit parts.
- All locales; changeset; 390/768/1280 light/dark screenshots; no merges or VRT approvals.

## Review focus
- Breakpoints 639/640/767/768/1023/1024 and coarse desktop.
- Failed save never sends or clears dirty state; created page receives stable identity.
- Paused/silenced/offline targets cannot silently receive mirror writes.
- H3 baseline cannot expose LED/palette features.
- Keyboard/picker focus, single mode toggle, no preview collapse or clipped tools.

## Task 1 — preview and safe target composition
Files: page-builder.tsx, new editor-touch.test.tsx, vitest coverage list.
- [ ] Write assertions for dock/pane, one mode control and H3 baseline fallback; observe failures.
- [ ] Compose EditorPreview with existing board; controlled persisted mode; move target controls into sensible host slots; mirror pane and More share state.
- [ ] Verify focused tests.

## Task 2 — kit toolbar wiring
Files: template editor toolbar adapter, TipTapTemplateEditor, CharsetTemplateEditor; toolbar tests.
- [ ] Test touch versus default, picker threshold and More mirroring slot before implementation.
- [ ] Wire kit components preserving local editor/draw behavior; compose primitives where kit cannot express exact threshold. Record gap.
- [ ] Verify toolbar and existing history/shortcut regressions.

## Task 3 — Save and Show now
Files: page-builder.tsx, page-editor-shell.tsx and route callbacks as needed; save/navigation tests.
- [ ] Test new-page guard, save-in-place, first-save toast and failed-save send protection before implementation.
- [ ] Reuse ChangePageDialog duration flow; save current edits before opening; keep editor mounted and advance revision/snapshot.
- [ ] Verify save and navigation regressions.

## Task 4 — evidence and review
- [ ] Independent locale/e2e work integrated; changeset and DD-W row.
- [ ] Full unit coverage, static checks/build, browser/axe and screenshots locally where supported; otherwise hosted e2e per batch ruling.
- [ ] Push normal PR into v11; Astra review <=3 rounds exact head; fix findings test-first, poll hosted CI until green or WRAPUP.
