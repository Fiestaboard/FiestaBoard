Find gaps in FiestaBoard's Playwright regression coverage by comparing the existing suite against `.claude/ux-tree.json`.

Use the `qa-auditor` agent. Optional argument: `<scope>` — limits the audit to nodes whose id starts with `<scope>.` (e.g. `pages`). With no argument, every node in the manifest is audited.

Prerequisite: `.claude/ux-tree.json` must exist. If it doesn't, run `/map-ux <scope>` first.

The agent (read-only) will:
1. Inventory every `*.spec.ts` under `web/tests/`.
2. For each test, extract title, `goto()` routes, and distinguishing selectors.
3. For each UX node in the manifest, assign a status:
   - **covered** — a test reaches the route and exercises the state.
   - **partial** — a test reaches the route but doesn't exercise this specific state.
   - **uncovered** — nothing touches this state.
4. Write `.claude/ux-coverage.json` with per-node verdicts, matching specs, and a summary (covered / partial / uncovered / coverage_pct).
5. Print a gap table grouped by status.

The agent will suggest `/stub-ux-tests` as the next step to scaffold the gaps.
