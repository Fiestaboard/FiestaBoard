# Editor touch pass implementation plan

> For agentic workers: use superpowers:executing-plans for application work; independent agents own e2e and locale files. User authorizes autonomous execution and final Astra review.

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
- [ ] Push normal PR into v11; Astra review <=3 rounds exact head; fix findings test-first, poll hosted CI until green or the owner wrap-up flag.

## Bounded parity continuation (2026-11-17)

Specification: external `program/reviews/pr-2501-figma-parity.md`, findings F2–F7. Preserve the frozen source review and completed 19-node live Figma evidence.

- [ ] Correct Colors accessible locator and explicit plugin/functions fixtures; settle one full Formula axe scan before diagnosing additional findings.
- [ ] Add failing landmark/cleanup/interaction regressions. Give touch toolbars a translated body-level region through kit container APIs.
- [ ] Diagnose contracted visual viewport geometry from actual rectangles; keep readable board tiles and distinguish synthetic evidence from native IME.
- [ ] Add failing H3 and empty-state interaction tests. Compose kit tools with working plain-text insertion, grouped warning/preview, disabled unsupported tools and starter actions.
- [ ] Verify shared kit Toaster adoption against a local alpha+409 build while preserving drawer/walkthrough/locale/theme and caller placement. Registry publication remains required; do not commit tarballs or app-specific styling.
- [ ] Run full coverage/static/build, serial browser flows, actual-route axe and every affected drawn state in both themes. Independently review exact head and inspect hosted layout artifact upload.
- [ ] Normal commit/push, observe final CI, update status/ownership; owner Fable/VRT/merge gates remain separate.
