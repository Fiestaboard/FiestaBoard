Add a new MCP tool, prompt, or resource on the `/api/mcp` endpoint.

Use the `mcp-tool-builder` agent. Required argument: the tool/prompt `<name>` (snake_case).

The agent will:
1. Trace existing patterns via recent PRs (#848, #852, #845, #836, #835, #858).
2. Verify a feature branch (`feat-mcp-<name>`).
3. Add the tool in `src/api_server.py` following the existing registry pattern.
4. Ensure output is a **structured dict** (PR #845 convention).
5. Preserve bearer-token auth and the `/auth/mcp-token` unblock path.
6. Add pytest tests, update README "26+ tools" section, and run a live `curl` smoke test against the dev container.

If no `<name>` is provided, ask before proceeding.
