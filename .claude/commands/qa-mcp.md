Verify the `/api/mcp` surface against documented conventions.

Use the `mcp-qa` agent. No required arguments.

The agent (read-only) will:
1. Confirm the dev container is up.
2. Read current `FIESTABOARD_AUTH_ENABLED` and `FIESTABOARD_MCP_TOKEN`.
3. Call `/api/mcp/list-tools` and `/api/mcp/list-prompts`; cross-check against the README "26+ tools" list (drift in either direction is flagged).
4. Verify every tool returns a structured dict (PR #845 convention).
5. Verify bearer-token gating when auth is enabled.
6. Verify `/auth/mcp-token` remains reachable when auth is disabled (PR #858 regression).
7. Run `pytest tests/ -k mcp`.

It will not edit source — it produces a punch list with owners.
