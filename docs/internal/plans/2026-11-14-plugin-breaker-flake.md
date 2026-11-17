# Plugin breaker flake implementation plan

Goal: remove scheduling assumptions from the slow-honest plugin test while retaining the real executor, cache, breaker and board context.

Scope: `tests/test_plugin_fetch_breaker.py` and a patch changeset. No product changes unless deterministic evidence shows a defect. The companion quarantine-recovery test retains its existing delayed helper.

- [ ] Reproduce the old scheduling failure by delaying only the old helper long enough that its fixed ticks finish first.
- [ ] Add an event-gated real PluginBase helper. Wait for fetch start before a real zero-duration futures wait, assert one timeout without quarantine, then release and poll the real cache with a 10-second deadline. Assert final board data, reset streak and one fetch.
- [ ] Prove sensitivity by temporarily breaking cache publication and timeout clearing, observing failures, and restoring production source.
- [ ] Run the target 200 times with xdist four workers and CPU stress; run full pytest, Ruff lint and format. Keep logs in the program status evidence directory.
- [ ] Commit with the required trailer, push normally and open a PR into v11. Request one independent gpt-6-astra review (at most two rounds), address findings, observe CI and update program status/worktree ownership. Never merge.
