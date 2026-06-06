Turn a failed GitHub Actions run into a one-screen findings table that points to the real error.

Use the `ci-failure-summarizer` agent.

Optional arguments:
- `--run <id-or-url>` — a specific run (numeric ID, full URL, or SHA prefix). Default: most recent failed run on the current branch.
- `--all` — show every failing job (default shows the first failure per stage to keep output compact).

The agent (read-only) will:
1. Resolve the run via `gh run list` / `gh run view`.
2. Identify failed jobs and map them to CI stages via `.github/workflows/`.
3. Fetch focused logs with `gh run view --log-failed` and apply per-stage extractors:
   - ruff: file:line:col error
   - pytest: `FAILED ::test_name` + assertion line + 5-line traceback
   - Vitest: ` FAIL ` block + expected/received
   - Playwright: `✘` marker + locator/expect block + trace artifact path
   - Storybook a11y: axe rule + selector
   - Docker build: failing `RUN` step
4. Deduplicate findings that share a root cause across jobs.
5. Surface a "likely root cause" only when one finding is clearly upstream of the others.

It will not rerun CI — that's your call after triaging.
