# GitHub Actions Sidebar Cleanup — Design

## Problem

The GitHub Actions sidebar (left nav at `https://github.com/<repo>/actions`) lists 15
workflows in alphabetical order by their `name:` field. Today the names are inconsistent —
some use `Claude:` as a category prefix, some don't; verbs and capitalization vary; manual
one-off workflows are visually indistinguishable from automatic CI runs. Scanning the
sidebar to find a specific workflow takes longer than it should.

## Goal

Apply a consistent `Prefix: Title-Case Name` convention across all workflow `name:` fields
so the sidebar groups related workflows together under shared prefixes. No behavior change,
no filename change — only the display string each workflow advertises to the Actions UI.

## Non-goals

- Renaming workflow **files** (would invalidate run-history URLs and any external references)
- Renaming **jobs** inside workflows (would break branch-protection required-check rules)
- Changing triggers, permissions, secrets, or any logic
- Reordering jobs or restructuring workflow YAML beyond the single `name:` line
- Removing the dormant "Notify Arthur" entry in GitHub's UI cache (the workflow file
  was deleted in PR #512; the leftover sidebar entry must be cleared manually in
  the GitHub web UI — not in this repo)
- Removing the `copilot-swe-agent` mention in `.claude/commands/triage.md` (it's a
  defensive bot-login classifier, not an active Copilot integration)

## Design

### Prefix taxonomy

| Prefix | Meaning | Workflows |
| --- | --- | --- |
| `Build:` | Container image builds | FiestaPi Image, FiestaUpdater |
| `CI:` | Automatic per-PR / per-push validation | Lint, Test & Build; Integration Tests |
| `Claude:` | Claude-driven automation | Code Assistant, Docs Audit, Docs Audit Feedback, Docs Auto-Review, Issue Triage, PR Changelog |
| `Manual:` | Human-triggered one-offs (workflow_dispatch only) | Bootstrap Visual Baselines |
| `PR:` | PR-lifecycle automations not driven by Claude | Auto-Label |
| `Release:` | Publishes & deploys | Deploy Docs Site, Publish Image |
| `Scheduled:` | Cron-primary maintenance | Maintenance |

### Rename map

| File | Current `name:` | New `name:` |
| --- | --- | --- |
| `bootstrap-visual-baselines.yml` | `Bootstrap Visual Regression Baselines` | `Manual: Bootstrap Visual Baselines` |
| `build-fiestapi.yml` | `Build FiestaPi image` | `Build: FiestaPi Image` |
| `build-fiestaupdater.yml` | `Build & Publish FiestaUpdater` | `Build: FiestaUpdater` |
| `ci.yml` | `CI` | `CI: Lint, Test & Build` |
| `claude-docs-audit.yml` | `Claude: Docs Audit` | (unchanged) |
| `claude-docs-review.yml` | `Claude: Docs Auto-Review` | (unchanged) |
| `claude-issue-triage.yml` | `Claude Issue Triage` | `Claude: Issue Triage` |
| `claude.yml` | `Claude: Code Assistant` | (unchanged) |
| `docs-audit-feedback.yml` | `Claude: Docs Audit Feedback Capture` | `Claude: Docs Audit Feedback` |
| `docs.yml` | `Deploy Docs` | `Release: Deploy Docs Site` |
| `integration-tests.yml` | `Integration Tests` | `CI: Integration Tests` |
| `pr-changelog.yml` | `Claude: PR Changelog Summary` | `Claude: PR Changelog` |
| `pr-label.yml` | `PR Auto-Label` | `PR: Auto-Label` |
| `release.yml` | `Release and Publish` | `Release: Publish Image` |
| `scheduled-maintenance.yml` | `Scheduled Maintenance` | `Scheduled: Maintenance` |

12 of 15 files change. 3 (`claude-docs-audit`, `claude-docs-review`, `claude.yml`)
already conform.

### Resulting sidebar order

```
Build: FiestaPi Image
Build: FiestaUpdater
CI: Integration Tests
CI: Lint, Test & Build
Claude: Code Assistant
Claude: Docs Audit
Claude: Docs Audit Feedback
Claude: Docs Auto-Review
Claude: Issue Triage
Claude: PR Changelog
Manual: Bootstrap Visual Baselines
PR: Auto-Label
Release: Deploy Docs Site
Release: Publish Image
Scheduled: Maintenance
```

## Risks & mitigations

- **Required status checks break.** Branch-protection rules in GitHub reference the
  `job` name (e.g. `ci-success`), not the workflow `name:`. This rename does not touch
  any job IDs, so required checks remain green.
  *Mitigation:* Diff verification — confirm no `jobs:` block keys are altered.
- **External links to workflow names rot.** The Actions sidebar URL is
  `?query=workflow%3A<name>`. Anything bookmarked using the old name will no longer
  filter. Acceptable cost; URLs that use the workflow file path (`workflows/ci.yml`)
  still work.
- **Run history continuity.** GitHub Actions groups runs by workflow **file path**, not
  `name:`. Renaming only the display field preserves history.
- **Stale UI entries.** Anyone still seeing "Notify Arthur" in their sidebar must clear
  it manually via the workflow's three-dot menu. Not in scope.

## Verification

After the edits land:

1. `grep -E "^name:" .github/workflows/*.yml` — confirm every file matches the rename
   map exactly (15 lines, including the 3 unchanged).
2. `git diff --stat .github/workflows/` — confirm every changed file is a one-line
   diff on the `name:` line. Anything larger means an accidental edit.
3. Branch CI runs to green — proves no required-check name was disturbed.
4. After merge, open the Actions sidebar in a browser and confirm the new grouping
   matches the "Resulting sidebar order" section above.
