# Security Audit Report — Merged Pull Requests

**Date:** 2026-02-28
**Scope:** PRs #136–#180 (30 merged pull requests)
**Auditor:** Automated security review

---

## Executive Summary

**30 pull requests** were reviewed for security vulnerabilities across 20 categories including hardcoded secrets, injection flaws, SSRF, authentication issues, CI/CD pipeline security, and more.

**No Critical or High severity issues were found.** A small number of Low/Info-level observations are documented below for awareness and potential hardening.

---

## Per-PR Review

### PR #180 — chore(deps): bump the docker-dependencies group with 2 updates
- Changes Docker base images: Python 3.11→3.14, Node 20→25
- **No security issues found.** Using updated base images is generally positive for security patches.

### PR #179 — Group Dependabot updates into single PRs per ecosystem
- Adds Dependabot grouping configuration.
- **No security issues found.**

### PR #178 — Fix docs deployment and PR auto-label workflow failures
- Switches docs deployment from `peaceiris/actions-gh-pages` with `personal_token` to native GitHub Pages (`actions/deploy-pages`). This is a **security improvement** — removes the need for a PAT.
- Adds error handling to PR label workflow.
- **No security issues found.**

### PR #177 — Deploy docs to fiestaboard.github.io instead of current repo's GitHub Pages
- Introduces cross-repo deployment using `personal_token: ${{ secrets.DEPLOY_TOKEN }}`. Properly stored as GitHub secret.
- **No security issues found.** Secret is referenced correctly.

### PR #176 — Reduce Dependabot frequency from daily to weekly
- Configuration-only change.
- **No security issues found.**

### PR #175 — Auto-merge Dependabot PRs on passing checks
- Auto-approves and merges patch/minor Dependabot PRs without human review.
- Uses `${{ secrets.GITHUB_TOKEN }}` properly. `PR_URL` passed as env var (not direct interpolation), preventing script injection.
- **Finding (Info — Supply Chain):** Auto-merging dependency updates without human review introduces supply chain risk. Mitigated by limiting to patch/minor only, using official `dependabot/fetch-metadata@v2`, and requiring CI checks to pass.

### PR #162 — Add docs deployment workflow with manual trigger
- Standard GitHub Pages deployment workflow with proper permissions.
- **No security issues found.**

### PR #161 — Configure Dependabot to run on a daily (nightly) schedule
- Dependabot configuration only.
- **No security issues found.**

### PR #160 — Fix flaky UI test: replace setTimeout-based autofocus with autoFocus attr
- Lock file changes only.
- **No security issues found.**

### PR #158 — chore(deps): bump qs from 6.14.1 to 6.14.2 in /docs-site
- Dependency bump (lock file only). `qs` updates often include security fixes for prototype pollution.
- **No security issues found.** This is a security improvement.

### PR #157 — fix(release): use lowercase owner for GHCR image tags
- **Finding (Low — CI/CD Script Injection):**
  - **File:** `.github/workflows/release.yml`
  - **Line:** `run: echo "owner_lower=$(echo ${{ github.repository_owner }} | tr '[:upper:]' '[:lower:]')" >> $GITHUB_OUTPUT`
  - **Issue:** Direct interpolation of `${{ github.repository_owner }}` in a `run:` shell step. While `github.repository_owner` is a trusted GitHub context restricted to valid usernames (alphanumeric + hyphens), best practice is to pass it as an environment variable to prevent potential shell metacharacter injection from expression contexts.
  - **Severity:** Low
  - **Type:** CI/CD pipeline security
  - **Recommendation:** Use `env:` block instead:
    ```yaml
    env:
      OWNER: ${{ github.repository_owner }}
    run: echo "owner_lower=$(echo "$OWNER" | tr '[:upper:]' '[:lower:]')" >> $GITHUB_OUTPUT
    ```

### PR #156 — Fix repo URL capitalization in visual_clock and last_fm manifests
- URL fix and validation test addition.
- **No security issues found.**

### PR #155 — Add docs deploy workflow for fiestaboard.github.io
- Uses `personal_token: ${{ secrets.RELEASE_PAT }}` for cross-repo deployment. Properly stored.
- **No security issues found.**

### PR #154 — chore: update repo references from roblesi to Fiestaboard org
- URL and ownership reference updates.
- **No security issues found.**

### PR #153 — docs: add referral link with discount to README
- Adds a Vestaboard referral link with code `vbref=ZDGYOT`.
- **No security issues found.** Not a vulnerability; referral links are common in open-source projects.

### PR #152 — Chore auto merge dependabot
- Initial Dependabot auto-merge workflow. Requires human approval before merge.
- **No security issues found.**

### PR #151 — fix(disney_parks_times): abbreviations sort order, uppercase, settings sort
- Plugin abbreviation logic changes and API response sorting.
- **No security issues found.**

### PR #150 — Docs README: wysiwyg editor and schedule + Disney Parks plugin
- Adds Disney Parks Queue Times plugin with API proxy endpoints.
- **Finding (Low — Unauthenticated Proxy Endpoints):**
  - **File:** `src/api_server.py`
  - **Endpoints:** `GET /queue-times/parks`, `GET /queue-times/parks/{park_id}/rides`
  - **Issue:** These endpoints act as an unauthenticated proxy to `queue-times.com`. While the base URL is hardcoded (no SSRF) and `park_id` is validated as `int` (no path traversal), the lack of authentication or rate limiting means anyone with network access could use these endpoints to make requests to Queue-Times.com through the server.
  - **Severity:** Low
  - **Type:** Exposed sensitive endpoints without auth / Missing input validation
  - **Mitigations already present:** Hardcoded base URL, integer type validation on `park_id`, 10-minute response cache (limits abuse), typical deployment is on local network.
  - **Recommendation:** Consider adding basic rate limiting or ensuring these endpoints are only accessible from the local network.

### PR #149 — feat(plugin): Disney Parks Queue Times from Queue-Times.com
- Full Disney Parks plugin implementation (same endpoints as PR #150).
- **Same finding as PR #150 above** (unauthenticated proxy endpoints).

### PR #148 — chore(deps-dev): bump qs from 6.14.1 to 6.14.2 in /web
- Dependency bump (lock file only).
- **No security issues found.**

### PR #147 — fix(weather): display UV index 0-11+ when API returns normalized 0-1 scale
- Weather UV index normalization logic. Safe type handling.
- **No security issues found.**

### PR #146 — chore(deps): bump markdown-it from 14.1.0 to 14.1.1 in /web
- Dependency bump (lock file only).
- **No security issues found.**

### PR #145 — Fix midnight rollover schedules and adjacent schedule overlap detection
- Schedule validation and overlap detection logic changes.
- **No security issues found.**

### PR #144 — docs(wsdot): add plugin display screenshot
- Binary image file addition only.
- **No security issues found.**

### PR #143 — feat(wsdot): WSDOT ferry plugin
- New WSDOT Washington State Ferries plugin.
- API access code handled properly: sourced from config or `WSDOT_API_ACCESS_CODE` env var, never hardcoded.
- All API URLs hardcoded to official WSDOT endpoints — no SSRF risk.
- `route_id` is integer validated — no path traversal.
- Proper request timeouts (15s).
- `api_access_code` field uses `"ui:widget": "password"` in manifest for UI masking.
- **No security issues found.**

### PR #141 — Docs contributing
- CONTRIBUTING.md documentation. Includes security guidance.
- **No security issues found.**

### PR #140 — Add Docusaurus documentation site with marketing landing page
- Static documentation site. No server-side code.
- **No security issues found.**

### PR #138 — Chore/gitignore and docs cleanup
- **Security improvements found:**
  - Added `client_id` and `client_secret` to `SENSITIVE_FIELDS` set in `config_manager.py` for masking in API responses.
  - Added `.env.local` and `.env.*.local` to `.gitignore`.
  - Created `SECURITY.md` with responsible disclosure guidance.
  - Created `RELEASE_CHECKLIST.md` with pre-release security review steps.
  - Removed `BULK_API_IMPLEMENTATION_SUMMARY.md` (temporary file cleanup).
- **No security issues found.** This PR is purely a security/hygiene improvement.

### PR #137 — Bump next from 16.1.4 to 16.1.6 in /web
- Dependency bump (lock file only).
- **No security issues found.**

### PR #136 — Bump lodash-es from 4.17.22 to 4.17.23 in /web
- Dependency bump (lock file only).
- **No security issues found.**

---

## Summary of All Findings

| # | PR | Severity | Type | Description |
|---|-----|----------|------|-------------|
| 1 | #157 | Low | CI/CD Script Injection | Direct `${{ github.repository_owner }}` interpolation in shell `run:` step. Should use env var instead. |
| 2 | #150, #149 | Low | Unauthenticated Proxy | `/queue-times/parks` and `/queue-times/parks/{park_id}/rides` endpoints act as unauthenticated proxy to external API. |
| 3 | #175 | Info | Supply Chain Risk | Auto-merging Dependabot patch/minor PRs without human review. Common practice but increases supply chain attack surface. |

### Statistics
- **Total PRs reviewed:** 30
- **Critical findings:** 0
- **High findings:** 0
- **Medium findings:** 0
- **Low findings:** 2
- **Info findings:** 1
- **Clean PRs:** 27

### Security Improvements Noted
- **PR #178:** Removed PAT-based deployment in favor of native GitHub Pages (reduced secret exposure)
- **PR #138:** Added `client_id`/`client_secret` to sensitive field masking, added `.env.local` to `.gitignore`, created `SECURITY.md` and release checklist
- **PR #158, #148, #146, #137, #136:** Dependency bumps that may include security fixes

### Recommendations
1. **PR #157:** Refactor the `run:` step to use an `env:` block for `github.repository_owner` interpolation.
2. **PR #150/149:** Consider adding rate limiting or network-level access controls to the Queue-Times proxy endpoints.
3. **PR #175:** Periodically review auto-merged dependency updates and consider enabling GitHub's dependency review action for additional supply chain protection.
