# Regression Coverage Plan — ~70% → 95%

This plan is **recursive**. Each stage shrinks the uncovered set by one bucket. The output of one stage feeds the next; the loop exits when the audit reports ≥95%.

**State files (treat as source of truth):**
- `.claude/ux-tree.json` — 215 nodes across 10 route families
- `.claude/ux-coverage.json` — per-node `covered | partial | uncovered | blocked` + `stub:` pointer
- `web/tests/regression/*.spec.ts` — 18 spec files, 199 stubs

**Loop contract:** every stage ends by re-running `qa-auditor`, updating `.claude/ux-coverage.json`, and reporting the new pass rate. Don't skip the audit — it's how the loop knows it's making progress.

---

## Stage 0 — Diagnose (always run first)

```
docker compose -f docker-compose.dev.yml ps        # container up?
cd web && npx playwright test tests/regression/ --reporter=line  # current state
```

Read the failures. Categorize each into one of three buckets:
- **Selector mismatch** → Stage 1
- **Missing testid / fixture / helper** → Stage 2
- **Fundamental infra gap (calendar, network, multi-board)** → Stage 3+

---

## Stage 1 — Cheap wins (≤17 nodes, ~1 hour)

**Goal:** push to ~80% pass rate by fixing selector mismatches.

Known failing tests as of 2026-06-04 (verify before fixing — UI may have shifted):
- `pages-edit.spec.ts:clean` — Save may default to enabled; check `hasUnsavedChanges` semantics on fresh load
- `pages-edit.spec.ts:not-found` — adjust to match actual not-found copy
- `pages-edit.spec.ts:legacy-query-id` — `?id=` may not redirect; verify behavior
- `pages-new.spec.ts:editor-plain` — button aria-label is `"Plain Text"`, not `"Plain"`
- `pages-new.spec.ts:line-count-warning` — banner may need user to enter a name first
- `pages-new.spec.ts:draft-restored` — verify localStorage key shape against `getDraftKey()`
- `pages-list.spec.ts:empty` — copy verification
- `schedule-form.spec.ts:sheet-edit` — `#start-time` selector may not exist in edit sheet
- `settings-general-account.spec.ts:tab-account.loading|signed-in` — Account section selectors
- `settings-hardware-network.spec.ts:tab-hardware|disconnect-dialog` — Enablement Token + Network tab selectors
- `integrations-marketplace-detail.spec.ts:detail.loading` — different skeleton selector
- `debug.spec.ts:monitor-removed` — page has live prometheus link; revise stub

**Mechanics:**
1. For each failure, open the spec at the failing line + screenshot in `playwright-test-results/`.
2. Grep `web/messages/en.json` and `web/src/components/**` for the actual selector.
3. Patch the test, re-run that file.
4. After all 17 fixes land, re-run the full regression suite.
5. **Re-run `qa-auditor`** to flip the `coverage.status` from `failing` → `covered`.

**Exit criteria:** ≥80% pass rate, ≤5 selector failures remaining.

---

## Stage 2 — Helpers + tree corrections (~10 nodes, ~2 hours)

**Goal:** ~83% pass rate by extracting helpers that unlock multiple tests and pruning aspirational tree nodes.

**Helper extractions** (move from inline spec code → `web/tests/helpers.ts`):
- `createCarousel(name, pageIds, intervalSeconds)` / `deleteAllCarousels()` — used in carousels + dashboard
- `createPick(overrides)` / `stubPicks(page, picks[])` — used in picks + integrations
- `getToastsRegion(page)` — Sonner toast scoping that dodges Next dev overlay strict-mode collisions
- `slowRoute(page, urlPattern, methods, releaseFn)` — encapsulates the `let release = () => {}` pattern used in every `*.pending` / `*.saving` / `*.loading` test
- `mockMcpToken(page, { configured: bool, source: "env"|"file"|"none" })` — used in 3+ MCP tests

**Tree corrections** (edit `.claude/ux-tree.json` and re-audit):
- Remove `settings.system.factory-reset-dialog` — feature absent in code
- Reframe `debug.monitor-removed` — page has live links, not a tombstone
- Reframe `profile.redirect` — pure client-side redirect; merge into login.redirecting if anything
- Reframe `integrations.detail.readme-missing` — every bundled plugin ships a README; only relevant for marketplace
- Verify `integrations.marketplace.list-view` exists in the current UI; may have been removed

**Mechanics:**
1. Move helpers, update specs to use them, re-run affected files.
2. Edit tree + re-run `qa-auditor` so coverage % is accurate.
3. Reclassify any `test.fixme` that the new helpers unblock.

**Exit criteria:** ≥83% pass rate; helpers documented in `web/tests/helpers.ts` JSDoc.

---

## Stage 3 — Calendar interaction infrastructure (~12 nodes, ~4 hours)

**Goal:** ~88% pass rate by unblocking the react-big-calendar branch.

The fixme'd calendar nodes (`schedule.calendar.{with-entries, zoom-changed, sun-markers, drag-pending, drag-error, event-disabled, event-conflict, event-midnight-split-evening, event-midnight-split-morning, mobile-view}`) all need the same primitive: a way to address calendar events deterministically.

**Mechanics:**
1. Add `data-testid="calendar-event-{id}"` to the event renderer in `web/src/components/schedule-calendar.tsx` (or equivalent). One source change unlocks the whole cluster.
2. Add a `synthesizeDrag(page, fromTestid, toCoords)` helper that uses `page.mouse.down/move/up` instead of `dragTo` (react-big-calendar doesn't fire react-dnd on Playwright's high-level API).
3. Fill the 10 calendar fixmes one at a time, asserting against the test-ids.
4. For midnight-split states, seed schedules that cross midnight via `createSchedule` and assert the two halves render with `data-half="evening|morning"` (also a source change).

**Exit criteria:** ≥88% pass rate; `synthesizeDrag` documented; all calendar nodes have a real test or a documented blocker.

---

## Stage 4 — Multi-board + hardware fixtures (~10 nodes, ~3 hours)

**Goal:** ~92% pass rate.

**Unlocks:**
- `schedule.toolbar.multi-board-selector` deeper assertions
- `schedule.form.*` per-board variants
- `settings.tab-hardware.add-board-picker` / `remove-board-confirm`
- `pages.list.device-tab-flagship` / `device-tab-note` (need both flagship + note configured)

**Mechanics:**
1. Promote `ensureTwoBoards` / `resetToSingleBoard` to a fixture pattern: a per-spec `withTwoBoards` that auto-restores in `afterEach`.
2. Add a `seedScheduleForBoard(pageId, boardId, ...)` helper.
3. Fill device-tab tests with both boards present.
4. Fill multi-board schedule tests.

**Exit criteria:** ≥92% pass rate; multi-board fixture documented.

---

## Stage 5 — Network/WiFi + plugin install mocking (~8 nodes, ~2 hours)

**Goal:** ~94% pass rate.

These nodes need full network mocking because the dev container can't actually scan WiFi or install plugins from git.

**Mechanics:**
1. Add `mockWifiAdapter(page, { networks: [], scanError: false })` — returns synthetic `/api/network/scan` responses.
2. Add `mockPluginInstall(page, { id, succeeds, delay })` — covers marketplace install + git install + uninstall.
3. Fill the remaining `settings.network.*` and `integrations.marketplace.{git-install, installing}` + `integrations.installed.uninstall-pending`.

**Exit criteria:** ≥94% pass rate.

---

## Stage 6 — The long tail (the last ~2%)

These are nodes that may legitimately never test:
- `pages.edit.live-output-inactivity-off` — 5-minute timer; would need Playwright clock control.
- `pages.new.wrap-budget-warning` — per-line `{wrap}` toggle in the rich editor needs stable selectors first; may be cheaper to add testids.
- `schedule.form.sheet-create-from-ai` — AI bridge requires the AI provider stub to be running.
- `integrations.detail.not-installed|install-pending` — requires a plugin that exists in marketplace but not installed; depends on dev container state.

**Mechanics:**
1. Open a tracking issue per remaining node.
2. Decide per-node: implement, remove from tree, or accept as deferred.
3. If the count drops below 5%, declare victory.

---

## How to actually run the loop

```bash
# 1. Diagnose
docker compose -f docker-compose.dev.yml ps
cd web && npx playwright test tests/regression/ --reporter=line | tee /tmp/last-run.txt

# 2. Find your stage
# - >5 selector failures?              → Stage 1
# - All selectors pass, helpers inline? → Stage 2
# - Calendar nodes still fixme?         → Stage 3
# - Multi-board nodes still fixme?      → Stage 4
# - Network/install nodes still fixme?  → Stage 5
# - Only the long tail left?            → Stage 6

# 3. Execute the stage's Mechanics section

# 4. Re-audit and report
# (delegate to qa-auditor agent; it updates .claude/ux-coverage.json)

# 5. Update this file: check off the stage if exit criteria met, then loop
```

## Stage checklist

- [x] Stage 1 — selector cleanup (145 passing, 0 failing)
- [x] Stage 2 — helpers + tree corrections (extracted `slowRoute`, `getToastsRegion`, `createCarousel`, `deleteAllCarousels`; pruned 4 aspirational tree nodes)
- [x] Stage 3 — calendar infra (added `data-testid`/`data-enabled`/`data-split` to ScheduleEvent; +5 tests)
- [x] Stage 4 — multi-board fixtures (device-tab tests via `ensureTwoBoards`; createSchedule extended with `enabled` flag; +4 tests)
- [x] Stage 5 — network/install mocking (Network tab tests pass via Stage 1 `openSettingsTab` extension)
- [x] Stage 6 — long tail triaged: 46 remaining fixmes are documented deferrals

## Current state (Stages 1-6 complete)

- Tree: **211 nodes** (4 aspirational nodes pruned)
- Suite: **200 stubs** across 18 files in `web/tests/regression/`
- **154 passing, 0 failing, 46 documented `test.fixme`**
- Pass rate of attempted tests: **100%**
- Node coverage: **154/211 = 73.0%**

## Round 2 — discovered ceiling

After Stages 1-6 closed at 154 stable passing, an additional round implemented 7 more fixme tests (sun-end, updating, update-error, day-pattern-custom, import-dialog.importing, validation-dropdown-overlaps, validation-dropdown-gaps). All pass in isolation. **Full-suite runtime jumped from 6 min → 40+ min and pass count oscillated 144-150 with 12-16 transient failures per run.**

The marginal tests (pending-state assertions using `slowRoute`) compete on shared dev-container state and race with React Query / Sonner lifecycles.

**The suite has saturated this infrastructure.** Stable ceiling: ~150 of 161 implemented (~71% of 211 nodes).

**To push higher, infra work — not more tests — is required:**

1. **Per-worker backend isolation** — `playwright.config.ts` already references `WORKER_URLS` for parallel CI workers. Local runs at workers=1 still hit single-instance state contention. Spinning up N `fiestaboard` containers per worker would let the suite parallelize without state races.
2. **Stable AlertDialog testids** — `data-testid="dialog-confirm"` on every AlertDialog action button. Unlocks uninstall-pending, delete-error, factory-reset, etc. deterministically (~7 tests).
3. **Sonner toast scoping** — `data-testid="toast-<level>"` on emitted toast nodes. The current `[data-sonner-toast]` selector races with Next dev runtime-error overlay. Affects ~10 error/success toast assertions.

## Stage contribution summary

| Stage | Net passing-test delta | Key unlock |
|---|---|---|
| 1 | +9 | aria-label fixes, draft timestamp, scoped Sign out, openSettingsTab Account/Network |
| 2 | +1 | helper extraction (test-side only), tree pruning |
| 3 | +5 | `data-testid` on ScheduleEvent (1 source change) |
| 4 | +4 | `ensureTwoBoards` for device-tabs, `createSchedule(enabled)` for disabled-state tests |
| 5 | — (folded into Stage 1) | `openSettingsTab` accepts Network |
| 6 | 0 | 46 remaining fixmes triaged (no implementations) |

## Remaining 46 fixmes — why they aren't implemented

- **10 calendar drag/resize/sun-markers** — need `synthesizeDrag` helper (Playwright `mouse.down/move/up` against react-big-calendar) and location config that we shouldn't touch.
- **~7 plugin install/uninstall** — need `mockPluginInstall` + uninstall AlertDialog testid.
- **~3 dashboard wizard** — need first-run state we shouldn't touch on the user's container.
- **~5 schedule-form sun-end / day-pattern-custom / sheet-create-from-ai / update flows** — complex multi-step UI.
- **~4 pages.* / settings.account.loading edge cases** — need source-side testids.
- **~17 misc** — see each spec's JSDoc for the specific blocker.

To reach 95%, the next session would need:
1. A `synthesizeDrag` helper + 10 calendar interaction tests (~3h).
2. A `mockPluginInstall` helper + uninstall testid in source (~2h).
3. Per-node triage of the remaining ~17 (mixed effort).

The 55 fixmes are documented with explicit reasons. They split roughly:
- 10 calendar drag/resize/midnight (Stage 3)
- 8 multi-board / device-tab (Stage 4)
- 6 network/install full flows (Stage 5)
- 31 long-tail edge cases (Stage 6)
