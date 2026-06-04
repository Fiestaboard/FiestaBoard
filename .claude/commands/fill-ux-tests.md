Implement and run the Playwright `test.todo` stubs under `web/tests/regression/`, turning gap stubs into real regression tests.

Use the `ux-filler` agent. Optional arguments:
- `--max <N>` — fill at most N stubs this run (default 5). Keeps batches small and reviewable.
- `--scope <subarea>` — limit to stubs whose UX node id starts with `<subarea>`.

Prerequisites: the dev container at `http://localhost:4420` must be up (the agent will offer to `/start` if not), and at least one `test.todo(...)` must exist under `web/tests/regression/`.

The agent will, per stub:
1. Read the JSDoc block (UX node id, route, preconditions, interactions, expected, source refs).
2. Read the referenced source components to learn real selectors.
3. Optionally probe the running app via Playwright MCP to confirm state reachability.
4. Flip `test.todo(...)` → `test(...)` and write a body that asserts the specific state — not just "page loads".
5. Run only the affected spec file in the container; if a test fails for a real app reason, mark the node `blocked` with `test.fixme` and continue rather than weakening the assertion.
6. Update `.claude/ux-coverage.json` (status → `covered` or `blocked`).

The agent will report pass / blocked counts and the remaining gap queue, and will not commit — you review, then commit or open a PR yourself.

Run repeatedly to chew through the gap list a batch at a time.
