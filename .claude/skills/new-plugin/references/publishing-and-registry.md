# Publishing & the registry

A plugin is invisible to FiestaBoard installs until it is **in the registry**, regardless
of how perfect the repo is. Two steps: publish the repo, then add a registry entry via PR
to the main FiestaBoard repo.

## 1. Publish the repo (gated — confirm with the user first)

Each of these is an outward, hard-to-undo action. Confirm before each.

```bash
# In the new ../fiestaboard-plugin--<slug> repo, on a clean `main`:
git add -A && git commit -m "feat: initial <name> plugin"

# Pick the owner — DON'T assume the Fiestaboard org. Default to the user's own account.
gh api user -q .login            # default owner = the user's login
gh api user/orgs -q '.[].login'  # orgs they belong to (Fiestaboard only for maintainers)
OWNER=<the-user's-login-or-an-org-they-can-create-in>

gh repo create "$OWNER/fiestaboard-plugin--<slug>" --public --source=. --push
gh run watch                     # confirm CI goes green on the default branch
```

- The repo **must** be named `fiestaboard-plugin--<slug>` and the manifest `id` must equal
  `<slug>` with hyphens→underscores. CI validation rejects mismatches.
- **Owner is per-contributor.** Only Fiestaboard maintainers can create under the
  `Fiestaboard` org; everyone else creates under their own account (or an org they have
  create-access to). The `repository` URL in the registry entry must use *that* exact
  namespace. The repo-name convention (`fiestaboard-plugin--<slug>`) applies regardless of owner.
- CI on the default branch is the **authoritative** test gate. The container run during
  development is the faithful local mirror, but the registry checklist requires green CI.

## 2. How the app consumes a registered plugin

For context (you don't implement this — it explains why the fields matter). The running app
reads `plugin-registry.json`, and on install does a shallow git fetch of the repo into
`external_plugins/<id>/`, then loads it like any plugin. It can auto-update by comparing
remote HEAD SHAs hourly. So the registry entry's `repository` + `id` are load-bearing: a
wrong URL or mismatched id means the install silently fails.

## 3. The registry entry

The registry is a single file in the **main FiestaBoard repo**: `plugin-registry.json`,
with a top-level `plugins` array. Add **one entry**, kept **alphabetical by `id`**. Exactly
these eight fields (no more, no less — every existing entry uses all eight):

```json
{
  "id": "tide_times",
  "name": "Tide Times",
  "description": "Display upcoming high and low tides for a coastal station.",
  "repository": "https://github.com/Fiestaboard/fiestaboard-plugin--tide-times",
  "author": "FiestaBoard Team",
  "fiestaboard_version": ">=4.2.0",
  "icon": "waves",
  "category": "weather"
}
```

| Field | Rule |
| --- | --- |
| `id` | `^[a-z][a-z0-9_]*$`; must equal the manifest id and the id derived from the repo name. |
| `name` | Display name. |
| `description` | One sentence (matches the manifest). |
| `repository` | `https://` GitHub URL; repo name must be `fiestaboard-plugin--<slug>`. |
| `author` | Author name. |
| `fiestaboard_version` | semver constraint `^(>=|>|<=|<|==|!=)\s*\d+\.\d+\.\d+$`, e.g. `">=4.2.0"`. |
| `icon` | Lucide icon name. |
| `category` | One of the seven categories. |

Also add a row to the **"All Available Plugins"** table in the main `README.md`
(alphabetical) — the human-readable mirror of the registry.

## 4. Validate before opening the PR

Run the same check CI runs, inside the FiestaBoard repo (or dev container):

```bash
python scripts/validate_plugins.py --registry --verbose
```

It enforces: `id` + `repository` present, repo name matches
`^fiestaboard-plugin--[a-z][a-z0-9-]*$`, `id` equals the id derived from the repo name,
valid `fiestaboard_version` constraint, `https://` only, repo reachability
(`git ls-remote`), and no duplicate ids. Fix anything it flags before pushing.

## 5. Open the PR (gated)

Per CLAUDE.md, **never commit registry changes directly to `main`.** Branch, commit, PR:

```bash
git checkout -b register-tide-times
git add plugin-registry.json README.md
git commit -m "feat: register tide_times plugin"
gh pr create --base main --title "feat: register tide_times plugin" \
  --body "Adds the Tide Times plugin (Fiestaboard/fiestaboard-plugin--tide-times) to the registry."
```

## Pre-registration checklist

Before the registry PR, confirm:

- [ ] Repo named `fiestaboard-plugin--<slug>`; manifest `id` matches (hyphens→underscores).
- [ ] `docs/board-display.png` is a **real** board render (not the scaffold placeholder).
- [ ] `manifest.json` has a `screenshots` array with exactly one `primary: true`.
- [ ] CI green on the default branch.
- [ ] Tests cover ≥70% (the standalone-repo gate; the platform's in-repo gate is 80%).
- [ ] `README.md` and `docs/SETUP.md` follow the canonical section order, TODOs filled.
- [ ] No real API keys, credentials, or personal info anywhere.
- [ ] Registry entry added alphabetically; `validate_plugins.py --registry` passes.
