# Releasing

FiestaBoard releases through [Changesets](https://github.com/changesets/changesets).
A release is a multi-arch Docker image (`fiestaboard/fiestaboard`, amd64 and
arm64), a `vX.Y.Z` tag and a GitHub Release. Stable releases also get a FiestaPi
image, a docs snapshot on fiestaboard.app, and a Docker Hub description update.
Nothing is published to npm. The root `package.json` is private and only carries
the version.

There are two channels:

| Branch  | Versions        | Docker tags                   | GitHub Release | Who gets it                    |
| ------- | --------------- | ----------------------------- | -------------- | ------------------------------ |
| `main`  | `10.4.0`        | `:10.4.0`, `:latest`          | latest         | every install on stable        |
| `alpha` | `10.4.0-beta.2` | `:10.4.0-beta.2`, `:beta`     | prerelease     | installs on the beta channel   |

The update checker (`src/system/update_service.py`) reads both Docker Hub tags
and GitHub Releases. Stable installs never see a prerelease, because it carries a
`-` and is excluded from `/releases/latest`. Beta installs see both kinds and
compare them by semver, so `10.4.0` is newer than every `10.4.0-beta.N`.

## Day to day

1. **Add a changeset to your PR.** Run `npx changeset`, select `fiestaboard`,
   pick `patch`, `minor` or `major`, and write one user-facing line. That line
   becomes the `CHANGELOG.md` entry and the GitHub Release notes. Commit the
   `.changeset/*.md` file it writes.
   - When the change releases nothing, run `npx changeset --empty` or add the
     **`no-changeset`** label. After adding the label, re-run the **Release
     guards** job.
   - CI's **Release guards** job fails a PR that changes shipped files without
     a changeset. "Shipped" means anything the Dockerfile copies into the image
     (`src/`, `web/`, `plugins/`, `requirements.txt`, the nginx and supervisord
     configs, and so on) plus `pi-image/`. Tests, Markdown, docs, CI, compose
     files and `fiestaupdater/` don't need one. The list is in
     `scripts/release/changeset_check.py`.
   - Dependabot PRs and Version PRs are exempt. Dependency bumps ride along
     with the next release. Add a changeset to a Dependabot PR when it should
     release on its own, for example a security fix.
2. **Merge as usual.** Nothing releases yet. The Release workflow opens or
   updates one **"chore: release"** PR (branch `changeset-release/main`). That
   PR consumes every pending changeset, bumps the version in `package.json`,
   `package-lock.json`, `web/package*.json` and `src/__init__.py`, and writes
   `CHANGELOG.md`.
3. **When you want a release, merge the "chore: release" PR.** The Release
   workflow builds the image from that commit and pushes the manifest. Only
   then does it create the tag and the GitHub Release, so no install is ever
   offered an image it can't pull. It then dispatches the FiestaPi build and
   the docs snapshot.

Many merges therefore share one image build, and the Version PR's diff shows
exactly what will ship and under which version.

Don't edit versions by hand. `scripts/version-sync.js` only copies the root
`package.json` version into the other files, and `npm run version-packages`
runs it after `changeset version`.

### Re-running a failed release

A push releases when `package.json`'s version has no GitHub Release yet. To
retry, use **Re-run failed jobs** on the failed run, or **Actions → Release →
Run workflow** on the branch. Once the multi-arch manifest for that version is
on Docker Hub, its architectures are not rebuilt. An existing tag is reused only
if it points at the same commit. The image is always built from the commit that
set the version (the Version PR's merge), not from the branch tip.

When the GitHub Release exists but a later step failed (the docs dispatch or
the FiestaPi dispatch), a fresh run sees the release and does nothing. Use
**Re-run failed jobs** instead.

The Version PR sits in the merge queue like any other PR. When another PR with
a changeset merges first, the action force-pushes `changeset-release/main`,
and the Version PR drops out of the queue. Queue it again.

## The alpha channel

`alpha` is a long-lived branch in Changesets **pre mode**: `.changeset/pre.json`
has `"mode": "pre", "tag": "beta"`. PRs into `alpha` follow the same
day-to-day flow. Its Version PR is titled "chore: release (beta)", and merging it
releases `X.Y.Z-beta.N` to `:beta` as a GitHub prerelease. Prereleases get no
FiestaPi image, no docs snapshot and no `:latest`.

The branch is `alpha` and the prerelease identifier is `beta`. The identifier
matches the app's "beta" update channel and continues the `vX.Y.Z-beta.N` tags
cut by the old `next` flow.

Guards (`scripts/release/pre_mode.py`):

- A PR into `main` fails if it would bring `pre.json` in pre mode. Exit mode is
  allowed, because that's the promotion.
- A PR into `alpha` fails if `pre.json` is missing or has a tag other than
  `beta`.
- The Release workflow on `alpha` fails without beta pre mode, and skips
  versioning and releasing in exit mode, so `alpha` never cuts a stable release.
- `scripts/release/plan.py` also refuses to release a prerelease version from
  `main` or a stable version from `alpha`.

### Betas must sort above stable

Beta installs take the newest version on either channel, so a beta whose
version sorts below the newest stable release is invisible to them. Worse, it
walks them back onto stable. In pre mode, Changesets computes the version from
the version `alpha` was created at plus the highest pending bump. So a
patch-only `alpha` created at `10.3.2` targets `10.3.3-beta.N`, and once `main`
ships `10.3.3` every later beta sorts below it.

- Start each cycle with a `minor` (or `major`) changeset, so betas target
  `10.4.0`. `main` keeps shipping `10.3.x` patches underneath without
  overtaking it.
- `scripts/release/plan.py` refuses to release a beta whose `X.Y.Z` is not above
  the newest stable release. When that fires, `main` has shipped past alpha's
  target. Restart `alpha` (Lifecycle, step 4).

### Lifecycle

1. **Create.** From `main`, right after a release:

   ```bash
   git switch -c alpha origin/main
   npx changeset pre enter beta
   git commit -am "chore(release): enter beta prerelease mode"
   git push -u origin alpha
   ```

   The first PR into `alpha` should carry a `minor` or `major` changeset (see
   above).

2. **Sync `main` into `alpha`** with a merge commit (not a squash), and only
   right after a `main` release, when `main` has no pending `.changeset/*.md`.
   Otherwise a stable changeset is consumed on both branches and appears in both
   changelogs. If `package.json`'s version conflicts mid-cycle, keep alpha's.
   Open the sync PR from `main` itself (head ref `main`). That makes it exempt
   from the changeset check.

3. **Promote to stable.**
   1. Open a PR into `alpha` that runs `npx changeset pre exit`, and merge it.
      Close alpha's open "chore: release (beta)" PR. The Release workflow now
      skips on `alpha`.
   2. Open a PR from `alpha` into `main`. Its `pre.json` is in exit mode, which
      `main` accepts. It is exempt from the changeset check (head ref `alpha`):
      its changesets were consumed by the betas and wait in `.changeset/pre/`.
   3. `main`'s next Version PR computes the stable version (say `11.0.0`),
      writes the changelog and deletes `pre.json`. Merge it to release to
      `:latest`. Beta installs graduate to it automatically, because `11.0.0`
      sorts above every `11.0.0-beta.N`.

4. **Restart alpha.** Delete `alpha` and recreate it from `main` (step 1).
   **Never merge `main` back into the old `alpha`.** `main` squash-merges, so
   the old branch keeps `.changeset/pre/` and its stale prerelease state. Its
   next beta would re-release old changesets at a version below the new stable
   one.

A breaking change on `alpha` is just a `major` changeset. The prerelease
version follows it (`11.0.0-beta.0`), so the old `BETA_TARGET_OVERRIDE` is no
longer needed.

## Repository settings this depends on

- **Claude bot app** (`CLAUDE_BOT_APP_ID` / `CLAUDE_BOT_APP_PRIVATE_KEY`) opens
  the Version PRs. A PR opened with `GITHUB_TOKEN` would have its CI gated in
  `action_required`.
- **`DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`** push the image.
- **`RELEASE_PAT`** dispatches the docs snapshot to
  `Fiestaboard/fiestaboard.github.io`. `GITHUB_TOKEN` can't dispatch across
  repositories. Releases no longer push to `main`, so the PAT is not needed for
  that.
- **`CLAUDE_CODE_OAUTH_TOKEN`** writes the stable release summary. The summary
  is optional, and the release ships without it if the call fails.
- **Rulesets.** `main` and `PR policy` target the default branch (merge queue,
  squash). `alpha` has its own ruleset: PR plus the required `CI Success`
  check, no merge queue, merge commits allowed (for syncs), and deletion allowed
  (for restarts).
- **FiestaPi.** `build-fiestapi.yml` is dispatched by the Release workflow with
  `release_tag`. It no longer listens for the release workflow's completion.

## Downstream FiestaUI upgrades

FiestaUI's Downstream Upgrade workflow opens the evergreen `fiestaui-upgrade` PR
into `main`. That PR changes `web/package*.json`, a user-visible change, so it
carries its own changeset (`.changeset/fiestaui-upgrade.md`), which FiestaUI's
workflow writes.

## History

Before Changesets, every merge to `main` that touched code cut a release.
`pr-label.yml` derived a `major`/`minor`/`patch` label from the PR title,
`release.yml` read it, ran `version-sync.js <bump>`, and pushed a `chore: bump
version to X.Y.Z [skip ci]` commit. If the image build failed, it force-pushed
`main` back. Betas came from a frozen `next` branch through a separate,
manually dispatched `release-beta.yml`, which derived the version from tags and
never committed it. The last beta from that flow is `v10.1.0-beta.1`.
