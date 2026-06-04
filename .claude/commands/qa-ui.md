Drive the web UI through golden-path flows and report regressions.

Use the `ui-qa` agent. Optional argument: `<area>` — one of `pages`, `schedules`, `plugins`, `integrations`. With no argument, all four areas are exercised.

The agent (read-only) will, via the Playwright MCP server:
1. Confirm `http://localhost:4420` is reachable (run `/start` if not).
2. Walk the golden path for each area, capturing screenshots into `/tmp/ui-qa/<timestamp>/`.
3. Read browser console; any `error`-level message is a FAIL.
4. Spot-check WCAG 2.2 AAA (focus rings, aria-labels, contrast) on at least one changed page.
5. Switch to at least one non-English locale and confirm no raw i18n keys leak.

It will not edit web code — it produces a punch list with owners.
