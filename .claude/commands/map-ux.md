Map the user-traversable UX of FiestaBoard into a structured manifest.

Use the `ux-mapper` agent. Optional argument: `<scope>` — one of `pages`, `integrations`, `schedule`, `carousels`, `settings`, `login`, `picks`, `dashboard`, `all`. If omitted, ask which area to map (default suggestion: `pages` for the vertical slice).

The agent (read-only) will:
1. Discover Next.js routes for the scope under `web/src/app/**/page.tsx`.
2. Read the route's component tree to find dialogs, sheets, tabs, view modes, empty / error / loading branches.
3. If `http://localhost:4420` is up, drive the running app via Playwright MCP to confirm the top discovered states are actually reachable.
4. For `integrations` / `all`, enumerate plugin-driven UI variants (configured / setup-required / config-sheet states), not one node per plugin.
5. Write `.claude/ux-tree.json` conforming to `.claude/ux-tree.schema.json`.

Each node has a stable id (`<area>.<subarea>[.<state>]`), the backing route, preconditions, interactions, and source file references. The downstream skills (`/audit-ux-coverage`, `/stub-ux-tests`, `/fill-ux-tests`) all read from this single file.

The agent will print a per-subarea summary and suggest `/audit-ux-coverage` as the next step.
