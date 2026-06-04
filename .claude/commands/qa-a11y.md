Audit the running FiestaBoard web UI for WCAG 2.2 AA accessibility issues.

Use the `a11y-web-auditor` agent. Optional argument: `<area>` — a single route like `dashboard`, `schedule`, `integrations`, `settings`, `login`, `pages`, `picks`, `carousels`, or `profile`. With no argument, every route is swept.

The agent (read-only) will, via the Playwright MCP server:
1. Confirm `http://localhost:4420` is reachable (run `/start` if not).
2. Run axe-core against each scoped route with the existing `wcag2a, wcag2aa, wcag21aa, best-practice` tagset.
3. Walk the page with the keyboard — focus order, visible focus ring, no traps.
4. Read the a11y tree (`browser_snapshot`) for landmarks, heading hierarchy, form labels, button vs link semantics.
5. Switch to `?lng=es` and `?lng=ja` and confirm `aria-label` strings translate and no raw i18n keys leak.
6. Exercise toasts / dialogs / live regions and verify announcements.

It will not edit web code — it produces an inline markdown findings table grouped by severity. Hand the output to `/fix-a11y` to ship the fixes.
