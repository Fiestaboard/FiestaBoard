Audit the FiestaBoard web UI for React render-performance issues.

Use the `render-perf-auditor` agent.

Optional arguments:
- `--scope <path>` — limit to a subtree (e.g., `--scope web/src/app/schedules`). Default: all of `web/src/`.
- `--max <N>` — cap findings (default: 20). Keeps reports actionable.

The agent (read-only) will scan for, in priority order:
1. **Tier 1** — Large-list rendering without virtualization (e.g., `ScheduleEntryForm`'s 1440 `SelectItem` children). Cross-references known hotspots from elevated `testTimeout` entries in `vitest.config.ts`.
2. **Tier 2** — Unstable TanStack Query keys (inline objects, non-memoized arrays).
3. **Tier 3** — Missing memoization on callbacks/props passed to `React.memo` children.
4. **Tier 4** — Expensive derivations not wrapped in `useMemo`.
5. **Tier 5** — Form re-renders caused by single-object state.

Findings come ranked by tier × visit frequency (route entries weighted higher). Recommendations stay within libraries already in use — no new vendors. Optional `--strict` runs `ANALYZE=true npm run build` to surface oversized chunks.

It will not edit files — hand findings to your follow-on workstream.
