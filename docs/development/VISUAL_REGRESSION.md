# Visual Regression Tests

FiestaBoard's web UI ships with Playwright visual regression tests
(`web/tests/visual-regression.spec.ts`). Each test renders a critical
UI state and compares it pixel-by-pixel against a committed baseline
PNG, using a 0.3 % pixel-diff ratio to tolerate sub-pixel rendering
differences between runs.

## When CI runs them

The `Run visual regression tests` step lives inside the `E2E Tests`
job in `.github/workflows/ci.yml`. It runs on every PR (and pushes to
`main`) when web-relevant paths change. The step uses `--workers=1`
because the 15-ish screenshot tests don't benefit from sharding.

## Updating baselines

You'll need new baselines when:

- You **intentionally redesigned** a UI surface that one of the tests
  exercises.
- A **library or font upgrade** caused acceptable rendering drift.
- You're **bootstrapping** the test suite for the first time.

There are two supported workflows. Pick whichever fits.

### Option A — locally (faster iteration)

Run the dev stack and regenerate from your laptop:

```bash
# 1. Start the dev container (per CLAUDE.md, never run npm/python on host).
docker-compose -f docker-compose.dev.yml up -d

# 2. Wait for the API to be ready.
curl --retry 30 --retry-delay 1 --retry-connrefused http://localhost:4420/api/health

# 3. Regenerate snapshots inside the container.
docker-compose -f docker-compose.dev.yml run --rm --profile test web sh -c "
  cd /web && npx playwright test visual-regression.spec.ts --update-snapshots --workers=1
"

# 4. Inspect the diff before committing.
git status web/tests/visual-regression.spec.ts-snapshots/
git diff --stat web/tests/visual-regression.spec.ts-snapshots/
git add web/tests/visual-regression.spec.ts-snapshots/
git commit -m "ci: refresh visual regression baselines"
```

Different local fonts can produce snapshots that disagree with CI. If
the resulting PR fails CI visual regression, fall back to Option B.

### Option B — via the bootstrap workflow (matches CI exactly)

```bash
gh workflow run bootstrap-visual-baselines.yml
```

The `Bootstrap Visual Regression Baselines` workflow:

1. Builds the production Docker image with the same arguments CI uses.
2. Boots a single `fiestaboard` + `mock-board` pair.
3. Runs Playwright with `--update-snapshots`.
4. Opens a PR titled **"ci: refresh visual regression baselines"** with
   the new PNGs.

Review the screenshots in the PR before merging. The workflow also
removes `continue-on-error: true` from the visual regression step on
first run — once merged, the step is **required**.

## Adding a new screenshot test

1. Add the test to `web/tests/visual-regression.spec.ts` using
   `expect(page).toHaveScreenshot(snap('your-name'), SCREENSHOT_OPTIONS)`.
2. Run Option A or B above to generate the baseline.
3. Commit the new `.png` alongside your test code.

## Why we hide the cursor / today highlight

`maskEditorCursor` and `maskCalendarToday` in the spec file neutralise
sources of non-determinism (blinking cursors, today highlighting).
Add similar masks if a new test surface has its own time-varying or
animation-driven state.
