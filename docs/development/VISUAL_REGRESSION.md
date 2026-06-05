# Visual Regression Tests

FiestaBoard's web UI ships with Playwright visual regression tests in
`web/tests/visual-regression.spec.ts`. Each test renders a critical UI
state and compares it pixel-by-pixel against a committed baseline PNG.
The suite uses `maxDiffPixelRatio: 0.003` (0.3 %) with a per-pixel
`threshold: 0.2` to tolerate sub-pixel rendering differences between
runs.

There are 15 screenshot tests covering Dashboard (default / dark /
light), Page Editor (empty / with content / with template variables),
Schedule (empty / with entries), Settings (general / board config),
Plugin Integrations (installed / marketplace), Pages list (empty /
with pages), and Navigation (sidebar default).

## When CI runs them

The `Run visual regression tests` step lives inside the `E2E Tests`
job in `.github/workflows/ci.yml`. It runs on every PR (and pushes to
`main`) when web-relevant paths change. The step uses `--workers=1`
because the 15 screenshot tests don't benefit from sharding.

The step is currently `continue-on-error: true` — see the comment block
in `ci.yml`. Once `bootstrap-visual-baselines.yml` has been run and the
generated baselines are merged, that line is removed and the step
becomes required.

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

# 3. Regenerate snapshots inside the web test container.
#    Working dir inside the container is /app (mounted from ./web).
docker-compose -f docker-compose.dev.yml --profile test run --rm web sh -c "
  npm ci && npx playwright test visual-regression.spec.ts --update-snapshots --workers=1
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

Review the screenshots in the PR before merging. Flipping the CI step
from advisory (`continue-on-error: true`) to required is a separate
one-line PR — the bot token in `bootstrap-visual-baselines.yml` lacks
the `workflow` scope needed to modify `ci.yml`.

## Adding a new screenshot test

1. Add the test to `web/tests/visual-regression.spec.ts` using
   `expect(page).toHaveScreenshot(snap("your-name"), SCREENSHOT_OPTIONS)`.
   Use the existing `snap()` helper so snapshot filenames stay consistent.
2. Run Option A or B above to generate the baseline.
3. Commit the new `.png` alongside your test code under
   `web/tests/visual-regression.spec.ts-snapshots/`.

## Why we hide the cursor / today highlight

`maskEditorCursor` and `maskCalendarToday` in the spec file neutralise
sources of non-determinism (blinking caret, selection highlights, the
calendar "today" tile that changes daily). Add similar masks if a new
test surface has its own time-varying or animation-driven state.

## Related files

- Spec: `web/tests/visual-regression.spec.ts`
- Baselines: `web/tests/visual-regression.spec.ts-snapshots/`
- CI step: `.github/workflows/ci.yml` (search for `Run visual regression tests`)
- Bootstrap workflow: `.github/workflows/bootstrap-visual-baselines.yml`
