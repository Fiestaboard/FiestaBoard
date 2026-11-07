# Release through Changesets with a prerelease channel

Status: proposed (2026-11-07). Port of the FiestaUI design merged in
Fiestaboard/FiestaUI#375 (`6a4de412`). This plan lives in `docs/internal/plans/`
rather than `docs/superpowers/plans/` because everything under `docs/` except
`docs/internal/` is published to fiestaboard.app and must carry YAML front matter.

## What FiestaBoard releases today

Nothing goes to npm. Root `package.json` is `"private": true`, and a release is:

| Artifact | Stable (`release.yml`, push to `main`) | Beta (`release-beta.yml`, `next`) |
| --- | --- | --- |
| Docker image `fiestaboard/fiestaboard` (amd64 + arm64, native runners, push-by-digest, then a manifest list) | `:X.Y.Z` + `:latest` | `:X.Y.Z-beta.N` + `:beta` |
| Git tag + GitHub Release | `vX.Y.Z`, AI summary (Claude), auto notes, install sections, `make_latest: true` | `vX.Y.Z-beta.N`, `prerelease: true`, `make_latest: false` |
| Docs site snapshot | `repository_dispatch` → `fiestaboard.github.io` | none |
| FiestaPi `.img.xz` | `build-fiestapi.yml` on `workflow_run` of "Release: Publish Image" | none |
| Docker Hub description | yes | none |

How the version is chosen today:

- **Stable.** `pr-label.yml` puts `major`/`minor`/`patch` on a PR from its
  conventional-commit title. After merge, `release.yml` reads the label of the
  PR that produced the commit, runs `scripts/version-sync.js <bump>` (root
  `package.json`, `web/package.json`, `web/package-lock.json`,
  `src/__init__.py`), and pushes `chore: bump version to X.Y.Z [skip ci]` to
  `main` with `RELEASE_PAT`. Every merge that is not all `paths-ignore`
  becomes a release. If the Docker build fails, `revert-on-failure`
  force-pushes `main` back.
- **Beta.** Paused. The workflow is disabled in Actions and `workflow_dispatch`
  only. It derives `X.(Y+1).0` from the newest stable tag (or
  `BETA_TARGET_OVERRIDE`), takes the next free `-beta.N` from git tags and Docker
  Hub, and never commits a version. `next` is frozen, 3 commits ahead of `main`,
  and its last beta is `v10.1.0-beta.1`.

The app depends on this through `src/system/update_service.py`. Stable
installs poll `/releases/latest` and Docker Hub tags without `-`. Beta installs
(channel `"beta"`) take the newest release or tag of any kind, compared by a
semver-ish `_parse_version`. `running_version()` prefers a prerelease `VERSION`
build-arg over `__version__`. Nothing in the app hard-codes the branch name or
the `beta` identifier. Ordering is generic semver.

## Target design

Two channels, both driven by Changesets:

| Branch | Mode | Versions | Docker tags | GitHub Release |
| --- | --- | --- | --- | --- |
| `main` | normal | `10.4.0` | `:10.4.0`, `:latest` | latest |
| prerelease branch (**`alpha`**) | pre mode, tag **`beta`** | `10.4.0-beta.0` | `:10.4.0-beta.0`, `:beta` | prerelease |

`:beta` stays the moving prerelease tag whatever `beta` is, because the app's
channel and the docs call it beta.

### Flow

1. A PR that changes what ships adds `.changeset/*.md` (`npx changeset`), with
   the `"fiestaboard"` package at `patch`/`minor`/`major` and one user-facing
   line. The line goes into `CHANGELOG.md` and the GitHub Release.
2. On push to `main` or `alpha`, `release.yml` runs `changesets/action@v2`
   with **no `publish-script`**. It opens or updates one "chore: release" Version
   PR (branch `changeset-release/<branch>`), which runs `npm run
   version-packages` (`changeset version && node scripts/version-sync.js`).
3. The same run then decides whether to release: **`package.json`'s version has
   no GitHub Release yet**. Only merging the Version PR changes that version,
   so many merges share one build.
4. If it releases, the run builds from `release_sha`, the last first-parent
   commit that changed `package.json`'s `version`. That is the Version PR's
   merge, not whatever happens to be at the tip. It pushes the manifest list
   first, then creates the tag and GitHub Release, so the update checker never
   offers a version whose image can't be pulled. For stable releases it then
   dispatches the docs snapshot, the Pi build, and the Docker Hub description.

The release is not gated on the action's `published` output. Because the
condition is "this version has no Release", re-running after a failed Docker
build just resumes, and per-arch builds already skip digests Docker Hub has.
This also sidesteps v2's "all changesets are empty" no-op and private-package
tagging semantics.

### Files

**Changesets config.**

- `.changeset/config.json`: `changelog` is `@changesets/changelog-github` with
  repo `Fiestaboard/FiestaBoard`, `baseBranch: main`, `commit: false`, and
  `privatePackages: { version: true, tag: false }`. Tags are created by our
  release job, not by Changesets.
- `.changeset/README.md`.
- Root `package.json` gains:
  - devDeps `@changesets/cli@^3` and `@changesets/changelog-github`;
  - scripts `changeset` and `version-packages`.
- `scripts/version-sync.js`: drop the bump modes (Changesets owns bumping). It
  also syncs the root `package-lock.json` root version fields and accepts
  prerelease versions.

**`.github/workflows/release.yml`.** The filename stays. The `name:` changes to
"Release", since nothing keys on it anymore.

- Trigger: `push: branches: [main, alpha]` plus `workflow_dispatch`, and no
  `paths-ignore`, because a changeset-only push must still update the Version
  PR. It is not `workflow_run`, because under `workflow_run` `GITHUB_REF` is the
  default branch.
- Concurrency: `release-${{ github.ref_name }}`, `cancel-in-progress: false`.
- Job `version`:
  - mint the Claude bot app token (`CLAUDE_BOT_APP_ID`/`_PRIVATE_KEY`);
  - checkout with `fetch-depth: 0`, then `npm ci` at the root;
  - on `alpha`, run `pre_mode.py branch-action`;
  - run `changesets/action@v2` with `github-token` set to the app token and no
    separate `GITHUB_TOKEN` env;
  - finally, the "Decide release" step, `scripts/release/plan.py`. It outputs
    `release`, `version`, `prerelease`, and `release_sha`. It fails if `main`
    carries a prerelease version or `alpha` carries a stable one.
- `build` (matrix) and `merge`: the existing jobs, with tags chosen by
  `prerelease`. `merge` also verifies that both architectures are present.
- `release`: tag `v$VERSION` at `release_sha`, then create the GitHub Release.
  - The body is built from the version's `CHANGELOG.md` section.
  - Stable releases keep the Pi banner, the Claude summary (now fed the
    changelog section), install sections, contributors, and the docs dispatch.
  - Prereleases get a beta notice, the changelog section, and install lines, and
    are created with `prerelease: true` and `make_latest: false`.
- `pi-image` (stable only): `gh workflow run build-fiestapi.yml --ref main -f
  release_tag=vX.Y.Z`.
- `dockerhub-description`: stable only.
- **Removed:**
  - `guard`, because there are no bump commits anymore;
  - label-based bump detection;
  - the version-bump push and the use of `RELEASE_PAT` to push `main`;
  - `revert-on-failure`. Force-pushing `main` is incompatible with Version PRs,
    and a failed build now leaves the version unreleased and re-runnable.

**`build-fiestapi.yml`.** Drop the `workflow_run` trigger. Every successful
release-workflow run would match it, including Version-PR-only runs and
prereleases. Add a `release_tag` input to `workflow_dispatch`, used for both
the version label and the release to attach to.

**Guards (Python, pytest-tested, run with bare `python3`).** These follow
FiestaBoard's existing workflow tests, so no extra test runner is needed in CI.

- `scripts/release/pre_mode.py`:
  - `check-base <ref>`: on `main`, a `pre.json` in pre mode fails, but exit
    mode is allowed because that is the promotion. On `alpha`, a missing
    `pre.json` or a tag other than `beta` fails.
  - `branch-action`: prints `skip` in exit mode and fails with no `pre.json`.
- `scripts/release/changeset_check.py <base> <head>`: fails a PR that changes
  shipped files without adding a changeset.
  - "Shipped" is an allowlist mirroring the Dockerfile's `COPY` sources:
    `Dockerfile`, `.dockerignore`, `requirements.txt`, `web/**`, `src/**`,
    `plugins/**`, `staff-picks/**`, `plugin-registry.json`,
    `plugin-previews.json`, `outputs.lock.json`, `scripts/seed_outputs.py`,
    `nginx.conf`, `starting.html`, `supervisord*.conf`, `entrypoint.sh`. It also
    covers `pi-image/**`, since the Pi image ships per release. Markdown and
    `tests/**` are excluded.
  - A test parses the Dockerfile's `COPY` lines so a new `COPY` can't silently
    escape the check.
  - `fiestaupdater/**` is not shipped. This keeps the #1969 / 8.36.0 lesson that
    `test_release_triggers.py` pinned.
  - Waivers:
    - the `no-changeset` label;
    - an empty changeset (`npx changeset --empty`);
    - head refs `changeset-release/*` (the Version PR);
    - head ref `main` (main→`alpha` syncs, whose changesets main already
      consumed);
    - head refs `dependabot/*`, because the image builds from the whole tree, so
      dependency bumps ride along with the next release. Add a changeset to a
      Dependabot PR when it should release on its own, such as a security fix.

**CI (`ci.yml`).** Add a `release-guards` job, modeled on FiestaUI's:

- it runs on `pull_request` and `merge_group`;
- the pre-mode check runs in both, and the changeset check runs only on
  `pull_request`;
- add the job to the `needs` of `CI Success`;
- add `scripts/release/**` to the `api` path filter so the guard tests run when
  the guards change.

**Downstream FiestaUI upgrade PRs.** FiestaUI's `downstream-upgrade.yml` force-pushes
the evergreen `fiestaui-upgrade` branch and opens a PR into `main`. It changes
`web/package*.json`, which is shipped, so it would fail the new check. Because
that is a user-visible UI change, the fix is to make it carry a changeset, not
to exempt it. A small companion PR in FiestaUI changes the "Reset evergreen
branch and bump" step: when the downstream repo has `.changeset/config.json`,
it writes `.changeset/fiestaui-upgrade.md` (`"fiestaboard": patch`, "Upgrade
the FiestaUI design system to vX") into the same commit. Because it checks for
the config file first, the two PRs can land in either order.

**Claude automation.**

- `CLAUDE.md` gets a Changesets section. Claude-run workflows read it.
- The PR-opening prompt in `claude-issue-triage.yml` says to write a
  changeset file for shipped changes. `claude-bug-hunt.yml` and
  `claude-a11y-audit.yml` only open issues, and their fixes come through
  triage. They can't use the interactive `npx changeset`, so they write the
  file directly.
- `docs-audit` only touches docs, so it is unchanged.

**Removed.**

- `release-beta.yml`, `tests/test_beta_release_workflow.py`, and
  `tests/test_release_triggers.py`. The last one's invariant moves into the
  changeset-check tests.
- The bump-label step in `pr-label.yml`. Area labels stay.
- The version-label buckets in `.github/release.yml`.
- `next` in `codeql.yml`, which becomes `alpha`.

**Docs.**

- `docs/internal/development/RELEASING.md` replaces `RELEASE_CHANNELS.md`. It
  covers day-to-day use, the prerelease lifecycle, promotion, restarts, re-runs,
  and the repo settings it depends on.
- Updates to `RELEASE_CHECKLIST.md`, `RASPBERRY_PI.md` (Pi trigger),
  `CONTRIBUTING.md`, and the PR template.

**Tests** (pytest, in `tests/`):

- `test_release_pre_mode.py` and `test_changeset_check.py`;
- `test_release_workflow.py`, which covers the shape of `release.yml`:
  - triggers;
  - per-branch concurrency;
  - action v2 with the app token;
  - no `publish-script`;
  - `:latest` only on stable;
  - stable-only Pi, docs, and description steps;
  - `target: runtime`;
- updated `test_docker_compose.py` expectations, if any.

## Verification before the PR

- Run `pytest` on the new and touched tests, and run the full `tests/` suite as
  CI does.
- Simulate in a scratch clone:
  - stable: add a changeset, run `npm run version-packages`, and check the four
    version files, `CHANGELOG.md`, and `plan.py` output;
  - pre: `changeset pre enter beta`, then a changeset, then `version-packages`,
    which should give `10.4.0-beta.0`. A second changeset should give `.1`.
    Then `pre exit` and `version` should produce the stable version and delete
    `pre.json`.
- Run `act pull_request -j release-guards` with event payloads for:
  - a PR into `main` with and without a changeset;
  - a PR with the `no-changeset` label;
  - a Version PR;
  - a PR into `alpha` with a bad `pre.json`.
- Run `act -n` on `release.yml` (the job plan) and `actionlint` on every
  touched workflow. The `version` job needs the app token and live GitHub, so
  its decision logic is covered by `plan.py`'s tests rather than an `act` run.
- Run an independent review (Fable subagent) of the diff.

## After merge (each repo-settings change confirmed with the user first)

1. Leave the frozen `next` branch alone for now (decided 2026-11-07: the prerelease branch is `alpha`). Archiving or deleting `next`, and removing the disabled "Release: Publish Beta Image" workflow entry, is a separate, confirmed step.
2. Create a `alpha-protection` ruleset, modeled on FiestaUI's `alpha-protection`
   (26773931):
   - PR plus the required `CI Success` check;
   - no merge queue;
   - merge, squash, and rebase all allowed (merge commits are needed for
     syncs);
   - deletion allowed (for restarts);
   - bypass for RepositoryRole 5 and Integration 4139279.
3. `git switch -c alpha origin/main && npx changeset pre enter beta`, then commit
   and push. The push needs the bypass or has to happen before the ruleset
   exists. The first Release run on `alpha` should pass the pre-mode guard
   and find nothing to release.
4. Land the FiestaUI companion PR.

## Decisions

- Prerelease branch: **`alpha`** (confirmed by the user, 2026-11-07).
- Pre tag: **`beta`**, so versions are `X.Y.Z-beta.N` (confirmed by the user, 2026-11-07).

## Changes after the plan review (independent Fable review, 2026-11-07)

- `plan.py` refuses to release anything whose `X.Y.Z` is not above the newest
  stable GitHub Release. In pre mode, Changesets bumps from the version `alpha`
  was created at, so a beta can otherwise sort below a stable release that
  `main` shipped mid-cycle. Beta installs would then ignore it and walk back
  onto stable (#1992). `RELEASING.md` says to open each cycle with a `minor`
  changeset, and to restart `alpha` when the guard fires.
- `plan.py` checks "already released" before the branch/version shape checks.
  This keeps the mid-promotion state (main briefly carrying the last, released
  beta) a no-op. A test covers it.
- Head ref `alpha` (the promotion PR into main) is exempt from the changeset
  check. Its changesets were consumed into `.changeset/pre/`.
- Playwright specs (`*.spec.ts[x]`, `web/tests/`) are not shipped.
- The release tag is created with `GITHUB_TOKEN`, so `build-fiestapi.yml`'s
  `vN.0.0` tag trigger doesn't fire a second Pi build next to the dispatch.
- `RELEASING.md` covers "Re-run failed jobs" after a partial failure, and the
  Version PR dropping out of the merge queue when another changeset lands.
