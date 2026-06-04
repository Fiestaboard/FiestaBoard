Exercise a plugin end-to-end against the running dev container.

Use the `plugin-qa` agent. Required argument: the plugin `<id>`.

The agent (read-only) will:
1. Confirm the dev container is up (`/start` if not).
2. Hit `/api/plugins/<id>/preview` and validate the live response.
3. Check declared template variables resolve in the response.
4. Verify `max_lengths` are not exceeded.
5. Confirm required `env_vars` are set in the container.
6. Run `scripts/run_plugin_tests.py --plugin=<id>` and report coverage vs 80% gate.
7. Verify each `screenshots[].src` exists under `plugins/<id>/docs/`.

It will not edit plugin or platform code — it produces a punch list with owners.

If no `<id>` is provided, ask before proceeding.
