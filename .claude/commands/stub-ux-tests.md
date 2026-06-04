Scaffold Playwright `test.todo` stubs under `web/tests/regression/` for every UX node marked `uncovered` or `partial` in `.claude/ux-coverage.json`.

Use the `qa-stubber` agent. Optional argument: `<scope>` — limit stubbing to nodes whose id starts with `<scope>.`. Default: every gap in the coverage report.

Prerequisites: `.claude/ux-tree.json` and `.claude/ux-coverage.json` must exist. If either is missing, run `/map-ux` and `/audit-ux-coverage` first.

The agent will:
1. Group gap nodes by subarea and emit one file per subarea (e.g. `web/tests/regression/pages-edit.spec.ts`).
2. Add a `test.todo(...)` per gap node, prefixed by a structured JSDoc block carrying the node id, route, preconditions, interactions, expected behavior, and source refs. The filler reads these next.
3. Reuse fixtures from `web/tests/helpers.ts` (`test`, `expect`, `configureBoard`, `API_URL`) — never re-implement.
4. Skip stubs that already exist (idempotent by `UX node: <id>` JSDoc marker).
5. Update `.claude/ux-coverage.json` to record each stub's location.
6. Run `npx playwright test web/tests/regression/ --list` to verify the stubs register without syntax errors.

The agent will suggest `/fill-ux-tests` as the next step.
