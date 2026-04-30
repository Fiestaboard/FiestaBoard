# CI `Detect Changed Paths` — Audit & Fix

## TL;DR

The `detect-changes` job in `.github/workflows/ci.yml` was supposed to skip
expensive jobs (Platform, UI, Plugins, A11y, E2E, Build) for docs-only PRs.
In practice, **every PR was triggering every job**, including E2E.

Root cause: the `shared` filter mixed positive globs with `!`-negation
patterns under `dorny/paths-filter`'s default `predicate-quantifier: some`.
With `some`, a filter is `true` if **any** pattern matches. A negation
pattern like `!.github/workflows/docs.yml` is satisfied by **any path that
isn't** `docs.yml`, which means *every file in the repo* matches the
`shared` filter. The exclusion list quietly turned the filter into a
universal match.

This document records what we found, the evidence, and the fix.

## Evidence

The user pointed at [PR #662 — "Promote Raspberry Pi flash as the headline
install path"](https://github.com/Fiestaboard/FiestaBoard/pull/662). That PR
modified only:

- `README.md`
- `docs-site/docs/intro.md`
- `docs-site/docs/setup/beginners-guide.md`
- `docs-site/docs/setup/quick-start.md`
- `docs-site/sidebars.ts`

None of those paths are in the `api`, `ui`, or `plugins` filters. Only
`docs` should have matched. Yet [run
25145428068](https://github.com/Fiestaboard/FiestaBoard/actions/runs/25145428068)
ran every CI job (Platform Tests, Plugin Tests, UI Tests, A11y Tests, E2E
Tests, Build Verification, Build Docs).

The `Detect Changed Paths` job log shows what `dorny/paths-filter` actually
reported:

```
Filter api      = false   Matching files: none
Filter ui       = false   Matching files: none
Filter plugins  = false   Matching files: none
Filter shared   = true    Matching files:
                            README.md
                            docs-site/docs/intro.md
                            docs-site/docs/setup/beginners-guide.md
                            docs-site/docs/setup/quick-start.md
                            docs-site/sidebars.ts
Filter docs     = true    Matching files:
                            docs-site/docs/intro.md
                            docs-site/docs/setup/beginners-guide.md
                            docs-site/docs/setup/quick-start.md
                            docs-site/sidebars.ts
```

`shared = true` matched **every changed file**, including a top-level
`README.md` that has nothing to do with CI. Because every downstream job is
gated on `... || shared == 'true'`, all of them ran.

## Root cause

The previous `shared` filter looked like this:

```yaml
shared:
  - 'docker-compose*.yml'
  - '.github/workflows/**'
  - '!.github/workflows/build-fiestapi.yml'
  - '!.github/workflows/build-fiestaupdater.yml'
  - '!.github/workflows/docs.yml'
  - '!.github/workflows/registry-scan.yml'
  - '!.github/workflows/pr-label.yml'
  - 'package.json'
  - 'scripts/version-sync.js'
```

The intent was: "treat all workflow files as shared, *except* the five that
build unrelated artifacts." That's not what the rules actually express.

`dorny/paths-filter` evaluates each filter against each changed file using
[picomatch](https://github.com/micromatch/picomatch). The action has a
`predicate-quantifier` setting that controls how multiple patterns combine:

- `some` (the default) — a file matches the filter if **any** pattern
  matches it.
- `every` — a file matches only if **all** patterns match.

A negation pattern like `!.github/workflows/docs.yml` matches *every path
except* `.github/workflows/docs.yml`. Under `some`, that single pattern is
enough to make the entire filter `true` for almost any file you can think
of — `README.md`, `docs-site/intro.md`, `LICENSE`, anything. The other
positive patterns and the other negations don't even need to fire.

In other words, the `!` lines were not subtracting from `.github/workflows/**`;
they were each independently saying "match everything except this one file",
which the `some` quantifier happily accepts.

The correct way to express subtraction with `dorny/paths-filter` is to set
`predicate-quantifier: every`, but that's a global setting and would break
the other filters (e.g. `api`, which legitimately wants `some` semantics so
that *any* of `src/**`, `requirements.txt`, `Dockerfile`, … triggers it).

## The fix

Drop the negations entirely and express `shared` as an **explicit allowlist
of files that genuinely affect every test surface**:

```yaml
shared:
  - 'docker-compose*.yml'
  - '.github/workflows/ci.yml'
  - '.github/workflows/integration-tests.yml'
  - 'package.json'
  - 'scripts/version-sync.js'
```

Workflows that own their own pipelines (`build-fiestapi.yml`,
`build-fiestaupdater.yml`, `docs.yml`, `registry-scan.yml`, `pr-label.yml`,
`release.yml`) are simply not listed, so editing them in isolation no
longer retriggers the app test suite. Any new workflow that *should* gate
the app pipeline can be added to the list explicitly — far easier to audit
than a deny-list of negations.

After the fix, the docs-only PR scenario from PR #662 evaluates as:

```
api      = false
ui       = false
plugins  = false
shared   = false   ← the fix
docs     = true
```

…which gates only `Build Docs` to run. Platform / Plugins / UI / A11y / E2E
/ Build Verification all skip, and `CI Success` still passes (its
aggregator treats `skipped` as success).

## Other findings (not changed in this PR)

While auditing the filters, a few smaller issues stood out. None are as
impactful as the `shared` bug, so they're recorded here for follow-up
rather than fixed in this PR.

### 1. `entrypoint.sh` and `nginx.conf` aren't in the `api` filter

Both ship in the production image and influence runtime behaviour, but
only the `ui` filter mentions `nginx.conf` and neither filter mentions
`entrypoint.sh`. A PR that only edits `entrypoint.sh` skips Platform Tests
and E2E. Consider adding `entrypoint.sh` to both `api` and `ui`, and
`nginx.conf` to `api` as well.

### 2. `integration-tests/**` doesn't trigger E2E

The `e2e-tests` job mounts `integration-tests/mock-board/` into the mock
container. A change to the mock board server has no path filter coverage,
so it skips E2E. Consider adding `integration-tests/**` to the `api` (or
a dedicated) filter.

### 3. `pyproject.toml` has no filter coverage

Python packaging / tool config lives in `pyproject.toml` but only
`requirements*.txt` and `.pylintrc` are in the `api` filter. Editing
`pyproject.toml` alone skips Platform Tests.

### 4. Plugin doc-only changes still run the full plugin suite

`plugins/**` is matched as a whole, so editing `plugins/foo/README.md`
re-runs manifest validation, registry validation, and every plugin's
test suite. Low-impact, but adding `- '!plugins/**/*.md'` and
`- '!plugins/**/docs/**'` would require switching the plugin filter to
`predicate-quantifier: every` (same caveat as in *Root cause* — that
setting is global and would break the other filters that legitimately
need `some` semantics), so it's not a drop-in change.

### 5. `release.yml` and `Dockerfile` interactions

`Dockerfile` is in both `api` and `ui` (correct — it builds both), but
`release.yml` is excluded from `shared` even though it ultimately ships
that Dockerfile. That's defensible — release runs its own checks — but
worth being explicit about in a comment.

## How to verify the fix

1. Open a PR that touches only `README.md` and/or `docs-site/**`.
2. In the `Detect Changed Paths` job log, confirm:
   - `Filter shared = false`
   - `Changes output set to ["docs"]` (or `[]` for non-docs-site doc changes)
3. Confirm Platform / UI / Plugins / A11y / E2E / Build Verification show
   as **Skipped** in the run summary, and `CI Success` is green.

## References

- `.github/workflows/ci.yml` — the workflow being audited
- [dorny/paths-filter README — predicate-quantifier](https://github.com/dorny/paths-filter#predicate-quantifier)
- [PR #662](https://github.com/Fiestaboard/FiestaBoard/pull/662) — the
  docs-only PR that motivated this audit
- [Run 25145428068](https://github.com/Fiestaboard/FiestaBoard/actions/runs/25145428068)
  — full job log showing `shared = true` matched `README.md` and the
  `docs-site/**` files
