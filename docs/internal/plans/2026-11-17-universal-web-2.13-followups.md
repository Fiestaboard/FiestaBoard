# Web 2.13 notification feedback follow-ups

> Execute test-first with a separate Astra whole-PR reviewer, at most two rounds. Owner requests autonomous work without questions.

**Goal:** Remove unused notification translations and distinguish failed push tests from skipped tests.

**Architecture:** Keep the existing FiestaUI status text and API contract. Select `testSent`, `testExpired`, `testFailed`, then `notSent` in that order; HTTP errors retain `testError`/`cooldown`. Add `testFailed` to all 14 locales and remove `working/notAvailableLabel`.

**Spec:** `FABLE-2524` non-blocking notes 1 and 2; shared `WEB-SLICE-BRIEF`; existing `DD-W113–115`. Jev selected client-only scope (0.99); no backend change.

**Constraints:** v11 base; patch changeset; no Figma writes, merges, publishing or comments. Use shared containers, one heavy process, Vitest max 2 workers, Playwright 1 worker. Check `WRAPUP` before each step.

## Steps

- [x] Add unit regressions for failed counts, skipped/all-zero fallback, sent/expired precedence and HTTP 429/503; observe RED for failed counts.
- [x] Remove the two unused keys from all 14 locales and add translated `testFailed`. Add the component branch and verify GREEN.
- [x] Add real-route failed-feedback browser cases at 390/768/1280 in both themes; assert status, axe, overflow and save captures. Run existing notification spec too.
- [x] Run full unit coverage, typecheck, lint, format and build; verify locale key parity and changeset.
- [ ] Independent Astra review (max 2 rounds), commit with required trailer, normal push and PR into v11. Observe CI; update program status/ownership.

## Review focus

Failure must not be mistaken for skip, expiry must retain re-enrollment guidance, accepted counts must not promise display, HTTP errors must remain distinct, and every locale must resolve the new key. Existing sign-out and refetch guards remain covered.
