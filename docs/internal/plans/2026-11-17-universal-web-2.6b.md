# Collection editor 07c implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task.

**Goal:** Complete the 07c editor around the merged Collection page list.
**Architecture:** CollectionForm owns draft state and the header/form layout; CollectionEditor wires saved-state evaluation and Show now. Existing FiestaUI components supply every primitive. Preserve existing draft protection and revision writes.
**Tech Stack:** React, FiestaUI alpha.2, TanStack Query, Vitest, Playwright.
**Spec:** program/briefs/WEB-SLICE-BRIEF.md, WEB-BATCH3-RULINGS.md and shots/web-2.6b/FIGMA-REFS.md in the universal-design hub.

## Global constraints

- DD-W22: collection-wide duration, shape-only page rows; no invented board association.
- DD-W23: prefer existing kit anatomy; record missing no-divider/small-meta options.
- No hub flag permits toggling no-repeat; capability false, switch hidden. Hub shuffle bags already avoid repeats.
- Dry-run evaluates saved state using cached data, not physical display state or drafts. Jev saved_evaluation p=1.00.
- No protected working-tree edits, merges, VRT approvals, comments, force pushes or release edits.

## Review focus

- Dirty rule drafts survive reorder attempts and prevent outer Save.
- Empty and deleted member pages do not produce a fabricated preview.
- Failed/unsupported saved evaluation displays unavailable; changed drafts hide stale results.
- Show now uses saved Collection and explicit display selection; never silently saves edits.
- Phone/tablet layouts retain editing and touch targets using existing kit controls.

### Task 1: Editor shell and form

- [ ] Add failing layout tests for header Save, segmented modes, button-driven member picker, no unsupported random switch.
- [ ] Implement responsive header and form card; retain custom duration validation and use one collection-wide control.
- [ ] Run form tests and fix existing assertions for the deliberate action/mode changes.

### Task 2: Variable rules

- [ ] Add failing menu reorder / no-HTML5-drag tests.
- [ ] Replace HTML5 drag and standalone icons with the rule menu and keyboard lift/move/drop/cancel model; preserve dirty draft protections.
- [ ] Render sentence-like compact summaries and authoritative saved rule results; keep autocomplete editing.

### Task 3: Saved evaluation and Show now

- [ ] Add API and pane tests, observe RED.
- [ ] Wire saved dry-run, page preview, stale/error/empty states, and shared ChangePageDialog through explicit display selection.
- [ ] Verify no side effects from preview; add e2e flow and axe assertions.

### Task 4: Verification and delivery

- [ ] i18n all 14 locales; changeset and coverage thresholds.
- [ ] Full vitest coverage, typecheck, lint, formatting, production build; Playwright one spec/one worker when Docker works.
- [ ] Capture 390/768/1280 light/dark implementation shots; inspect against refs.
- [ ] Push PR into v11, exact-head Astra review (maximum 3 rounds), wait/fix CI to green or the wrap-up signal.
- [ ] Record actual outcomes, deltas and follow-ups in status and WORKTREES.
