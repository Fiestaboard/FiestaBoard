# Flexible editor authentication recovery implementation plan

> **For agentic workers:** Use superpowers:executing-plans with TDD and independent review.

**Goal:** Keep a flexible draft open after authentication fails and give an actionable, truthful recovery path.

**Architecture:** Opt out of the existing automatic login redirect only for the flexible editor's create, update and preview requests. Show one persistent recovery notice for an actual 401, linking to sign-in in a separate tab. Retain explicit Save and preview retry; keep server authorization and every other caller's defaults unchanged.

**Tech Stack:** React, FiestaUI 8.15, TanStack Query, Vitest/MSW and isolated Playwright acceptance.

**Spec:** The authorized follow-up to real authenticated acceptance on `6c62c1f0f`: close the discoverability gap without automatic mutation replay, new persistence or authentication security changes. Jeffrey delegated design decisions to Astra, which approved the bounded approach below.

## Approaches

Adding text after the shared redirect would still expose the native leave warning before the recovery instructions. The selected approach keeps these editor requests in place and uses the existing `skipAuthRedirect` option. A persistent draft store or shared authentication redesign is unnecessary for this scope.

## Global constraints

- Same isolated feature branch and draft PR against `next`; no shared branch update, merge, deployment or live data.
- No dependency installation, credentials changes, automatic save replay or draft restoration promise.
- Only real `ApiError.status === 401` triggers sign-in guidance. A 403 remains a permission error; a 412 remains a revision conflict.
- Sign-in link uses `appUrl("/login")`, a native new-tab link and `noopener noreferrer`.
- Keep data only in the currently open editor; closing or reloading can discard unsaved changes.

## Review focus

- Preview-only 401 while the mobile preview is collapsed must still show guidance in persistent actions.
- New-page create and existing-page update must retain their unsaved content and original revision.
- Successful retry clears obsolete guidance; signing in alone must never save the document.
- Returning focus must not let unrelated background queries silently discard a dirty draft.
- Invalid explicit preview targets must not be presented as a successful primary-board preview; this separate backend correction is tested independently.

## Task 1: Bounded editor recovery

**Files:** `web/src/lib/api/pages.ts`, `web/src/components/flexible-page-editor/index.tsx`, locale messages, `web/src/__tests__/flexible-page-editor-auth.test.tsx`, `web/src/__tests__/api-auth.test.ts` and affected editor assertions.

**Interface:** Optional `{ skipAuthRedirect?: boolean }` on `createPage`, `updatePage` and `previewFlexiblePage`; existing callers retain their default behavior.

- [x] Add failing real-client/MSW component regressions for create/update/preview 401, 403 distinction, draft retention and explicit retry. Retain default API redirect coverage.
- [x] Run the focused tests and capture the intended failures before product edits.
- [x] Implement the narrow options and one persistent notice with a prefix-aware new-tab sign-in link.
- [x] Run focused tests, then the complete frontend suite, lint/types/format/build and docs checks.
- [x] Reproduce real expiry and permission failures in the isolated authenticated instance, verify no redirect/unload for editor requests and no automatic save after sign-in; have Astra review the rendered result.

## Task 2: Explicit preview target contract

- [x] Independently reproduce an explicitly invalid target falling back to the primary board. Reject explicit unknown/empty IDs consistently while preserving omitted/null target defaults; record the exact mobile-facing contract.
- [x] Run targeted and aggregate backend checks, regenerate the API reference when its contract changes, and review the combined diff.

## Delivery

Publish only after local checks and review. Monitor CI on the exact new commit and record the terminal results in the PR/handoff. Keep hardware and companion release gates explicit. The test runtime uses synthetic credentials/data in temporary memory, no published ports and no outbound network; remove only that owned runtime after acceptance.

## Verification record

- Intended RED failures captured for missing recovery guidance, an explicit empty preview target, out-of-order preview responses and authenticated error retries.
- Final complete frontend suite exited 0. A transient execution-session disconnect truncated the console log; the test container continued, its source hashes matched the reviewed files, and its exit status was recovered without restarting it.
- Final focused frontend coverage: 49 passed, including 12 real-client authentication component regressions.
- Backend aggregate: 15,036 passed and 2 skipped, with integration tests excluded as in the main CI unit job. The 76 targeted backend cases, generated API reference guard, lint and formatting passed.
- Real authenticated browser acceptance: six flows passed with synthetic memory-only data and isolated networking. Expired Save caused zero native leave prompts; signing in alone did not save. A subsequent revision conflict retained the draft and did not overwrite newer content.
- Astra independently reviewed three rendered expiry cases: desktop light/dark and a short phone with an invalid JSON draft. First-line repair focus remained reachable. Mobile software keyboards and longer translations remain outside these checks.
- Independent source review reproduced two response-ordering failures and obsolete sign-in guidance on protected validation errors. Request-order tracking and confirmed authentication outcomes resolve them; final re-review has no findings.
- Drafts are retained only in the open editor. No restoration after closing/reloading, automatic save, server-authentication change, deployment or live-display action was added.
