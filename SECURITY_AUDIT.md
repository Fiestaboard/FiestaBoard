# Security Audit Report — Merged Pull Requests

**Audit Date:** 2026-02-28
**Auditor:** Automated Security Review (Cloud Agent)
**Scope:** PRs #326, #327, #329, #331, #332, #333, #334, #335, #336, #338, #340, #341, #342, #344, #345

---

## Per-PR Analysis

### PR #345 — Move hamburger menu icon to left of header in mobile viewport
- **Files changed:** `web/package-lock.json`, `web/src/components/navigation-sidebar.tsx`, `web/src/components/wizard/setup-wizard.tsx`
- **Security issues found:** None
- **Notes:** Pure UI layout refactor — moves the hamburger menu button before the logo in mobile header. No new endpoints, no data handling changes.

---

### PR #344 — Allow skipping board setup in wizard and show unconfigured banner on dashboard
- **Files changed:** `web/src/__tests__/home-page-banner.test.tsx` (new), `web/src/__tests__/mocks/handlers.ts`, `web/src/app/page.tsx`, `web/src/components/wizard/setup-wizard.tsx`
- **Security issues found:** None
- **Notes:** Adds a "Skip for now" button to the setup wizard and an info banner on the dashboard when the board is not configured. Calls the existing `/api/config/validate` endpoint. No new auth surface; no sensitive data handling.

---

### PR #342 — Cache Docker image by content hash to skip redundant builds
- **Files changed:** `.github/workflows/ci.yml`, `.github/workflows/integration-tests.yml`, `web/package-lock.json`
- **Security issues found:** None
- **Notes:** Adds Docker image caching in CI via `actions/cache@v4` with content-based hash keys. The cached images are tarball exports stored in GitHub Actions cache (scoped to the repository). Build args only set `VERSION=dev`. Cache scoping (`scope=build-test`) separates test images from production builds. No secrets are baked into the cached images.

---

### PR #341 — perf: build template context once in batch preview instead of per-page
- **Files changed:** `src/api_server.py`, `src/pages/service.py`, `tests/test_api_extended.py`, `tests/test_pages.py`
- **Security issues found:** None
- **Notes:** Performance optimization that builds plugin data (template context) once for batch page previews instead of per-page. The new `preview_pages_batch` method on `PageService` accesses `template_engine._build_context()` (a private method) — this is a code quality concern but not a security issue. Error handling propagates `str(e)` in error responses, which was already the existing behavior prior to this PR.

---

### PR #340 — Graceful sheet/tray animation with opacity fade and slower timing
- **Files changed:** `web/src/__tests__/active-page-display.test.tsx`, `web/src/components/active-page-display.tsx`, `web/src/components/ui/sheet.tsx`
- **Security issues found:** None
- **Notes:** Pure CSS animation timing adjustments (300ms → 400ms for slide animations, 200ms → 300ms for overlay). No security impact.

---

### PR #338 — Fix devcontainer Dockerfile path resolution
- **Files changed:** `.devcontainer/devcontainer.json`
- **Security issues found:** None
- **Notes:** One-line fix changing the dockerfile path from `.devcontainer/Dockerfile` to `Dockerfile` in the devcontainer config. No security impact.

---

### PR #336 — ci: eliminate redundant jobs and fix npm caching across workflows
- **Files changed:** `.github/workflows/ci.yml`, `.github/workflows/integration-tests.yml`, `.github/workflows/pr-label.yml`, `requirements.txt`
- **Security issues found:** None
- **Notes:** This PR is a **security improvement** in several ways:
  - Switched from `rm -rf node_modules package-lock.json && npm install` to `npm ci` — deterministic installs from the lockfile prevent supply chain drift.
  - Removed testing dependencies (`pytest`, `pytest-cov`) from `requirements.txt` (production deps), moving them to `requirements-dev.txt` — reduces attack surface in production images.
  - Added `timeout-minutes` to CI jobs — prevents runaway jobs.
  - Added proper `cache-dependency-path` for pip and npm caches — ensures cache isolation.
  - Removed unnecessary `actions/checkout` from the `pr-label.yml` workflow — reduces unnecessary code checkout exposure.
  - Test env vars (`BOARD_READ_WRITE_KEY: test_key`, `WEATHER_API_KEY: test_key`) are clearly marked test values, not real credentials.

---

### PR #335 — Add Codespaces devcontainer configuration
- **Files changed:** `.devcontainer/Dockerfile` (new), `.devcontainer/devcontainer.json`, `.devcontainer/post-create.sh` (new)
- **Security issues found:** 2 (Info-level)

| # | Severity | Type | File | Description |
|---|----------|------|------|-------------|
| 1 | **Info** | Unsafe install pattern | `.devcontainer/Dockerfile` (line 18) | Uses `curl -fsSL https://deb.nodesource.com/setup_22.x \| bash -` (pipe-to-bash pattern). An MITM or compromise of `deb.nodesource.com` could inject arbitrary code. This is the standard NodeSource install method and is in a **dev container only** (not production), so risk is low. Consider using the official Node Docker image or verifying GPG signatures for defense-in-depth. |
| 2 | **Info** | Audit skipped | `.devcontainer/post-create.sh` (line 11) | Uses `npm install --legacy-peer-deps --no-audit` which skips the npm security audit during dependency installation. Acceptable in dev containers for speed, but means known vulnerabilities in newly installed packages won't be flagged during setup. |

---

### PR #334 — Remove header blur animations and add card fade-in animations across all pages
- **Files changed:** `web/src/app/integrations/page.tsx`, `web/src/app/page.tsx`, `web/src/app/pages/page.tsx`, `web/src/app/schedule/page.tsx`, `web/src/app/settings/page.tsx`, `web/package-lock.json`
- **Security issues found:** None
- **Notes:** Removes `BlurText` component usage from page headers and adds `animate-card-fade-in` CSS classes to cards. Pure UI/animation changes.

---

### PR #333 — fix: resolve Playwright strict mode violation in E2E setup wizard tests
- **Files changed:** `web/tests/integration.spec.ts`, `web/tests/multi-board.spec.ts`
- **Security issues found:** None
- **Notes:** Changes Playwright selectors from `getByText("Setup Complete!")` to `getByRole("heading", { name: "Setup Complete!" })` for stricter element matching. Test-only changes.

---

### PR #332 — chore: remove AI slop, stale docs, and fix outdated config/branding
- **Files changed:** 30+ files (mostly deletions of stale docs, plans, and screenshots docs)
- **Security issues found:** None
- **Notes:** Large cleanup PR that:
  - Deletes a speculative analytics plan (`.cursor/plans/ANALYTICS_PLAN.md`, `.cursor/plans/discord-community-plan.md`) — good hygiene, removes speculative architecture docs.
  - Deletes `config.example.json` which contained **only placeholder values** (`"your-local-api-key"`, `"your-weatherapi-key"`, `"your-long-lived-access-token"`, `"guest-password"`). These are clearly example/template values, not real credentials.
  - Updates branding from "Vesta" to "FiestaBoard".
  - Removes stale documentation files and screenshot placeholder docs.
  - Fixes outdated port references (6969 → 4420).
  - Simplifies `package.json` dev scripts.
  - No real credentials, no sensitive data exposure.

---

### PR #331 — chore(deps): Bump lucide-react from 0.564.0 to 0.575.0
- **Files changed:** `web/package-lock.json`
- **Security issues found:** None
- **Notes:** Standard dependency version bump for the Lucide icon library. Only `package-lock.json` changes with updated resolved URLs and integrity hashes.

---

### PR #329 — Remove auto dependabot merge workflow
- **Files changed:** `.github/workflows/merge-dependabot.yml` (deleted)
- **Security issues found:** None — this is a **security improvement**
- **Notes:** Removes a workflow that would automatically approve and auto-merge Dependabot PRs for patch/minor updates using `gh pr review --approve && gh pr merge --auto --squash`. Removing this means all dependency updates now require manual human review before merging, which is better security practice for supply chain security. The deleted workflow used `${{ secrets.GITHUB_TOKEN }}` with `contents: write` and `pull-requests: write` permissions — removing it reduces the automated use of write permissions.

---

### PR #327 — chore(deps): Bump the github-actions-dependencies group with 3 updates
- **Files changed:** `.github/workflows/release.yml`
- **Security issues found:** None
- **Notes:** Updates three GitHub Actions to newer versions:
  - `actions/upload-artifact` v4 → v6
  - `actions/download-artifact` v4 → v7
  - `peter-evans/dockerhub-description` v4 → v5
  
  These are standard version bumps to maintained actions. Using pinned major versions is acceptable for first-party and well-known actions.

---

### PR #326 — chore(deps): Bump node from 22-alpine to 25-alpine
- **Files changed:** `Dockerfile`
- **Security issues found:** None
- **Notes:** Single-line change updating the Node.js base image for the UI build stage from `node:22-alpine` to `node:25-alpine`. Node 25 is a current (non-LTS) release line. While production systems typically prefer LTS versions for longer security support, this image is used only as a build stage (`ui-builder`) — the runtime image uses a different base. No direct security vulnerability introduced.

---

## Summary

| PR | Title | Issues Found | Severity |
|----|-------|-------------|----------|
| #345 | Move hamburger menu icon to left of header | None | — |
| #344 | Allow skipping board setup in wizard | None | — |
| #342 | Cache Docker image by content hash | None | — |
| #341 | Build template context once in batch preview | None | — |
| #340 | Graceful sheet/tray animation | None | — |
| #338 | Fix devcontainer Dockerfile path | None | — |
| #336 | Eliminate redundant CI jobs | None (improvements) | — |
| #335 | Add Codespaces devcontainer config | 2 findings | Info |
| #334 | Remove header blur, add card fade-in | None | — |
| #333 | Fix Playwright strict mode violation | None | — |
| #332 | Remove AI slop, stale docs, fix config | None | — |
| #331 | Bump lucide-react | None | — |
| #329 | Remove auto dependabot merge workflow | None (improvement) | — |
| #327 | Bump github-actions-dependencies | None | — |
| #326 | Bump node from 22-alpine to 25-alpine | None | — |

### Overall Findings

- **Critical:** 0
- **High:** 0
- **Medium:** 0
- **Low:** 0
- **Info:** 2 (both in PR #335, devcontainer only — pipe-to-bash install pattern and `--no-audit` flag)

### Security Improvements Noted

Two PRs actively **improved** security posture:
1. **PR #329** — Removed auto-merge for Dependabot PRs, requiring manual review for all dependency updates (supply chain security improvement).
2. **PR #336** — Switched CI from `npm install` to `npm ci` (deterministic builds), separated test/dev dependencies from production requirements, and added job timeouts.

### Conclusion

No actionable security vulnerabilities were found across the 15 reviewed PRs. The codebase changes are clean: no hardcoded secrets, no credential leaks, no injection vulnerabilities, no auth bypasses, no SSRF/XSS/path traversal issues, and no unsafe patterns in production code. The two Info-level findings in PR #335 are limited to the development container and follow common industry patterns.
