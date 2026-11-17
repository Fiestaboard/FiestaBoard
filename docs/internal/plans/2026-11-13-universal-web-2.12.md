# Web 2.12 setup parity implementation plan

**Goal:** Implement the 07e/07d web setup, add-display, session, QR and activation flows using FiestaUI.
**Architecture:** Preserve existing setup and authentication services. Compose published kit parts for local Figma frames, and record missing kit APIs. Keep phone pairing in a dedicated component with CSRF mutations and bounded polling.
**Spec:** Program hub briefs/WEB-SLICE-BRIEF.md, WEB-BATCH3-RULINGS.md and shots/web-2.12/FIGMA-REFS.md.
**Tech stack:** React Router, React, FiestaUI alpha.2, i18next, Vitest, Playwright.

## Constraints

- Work only in dedicated cx- worktrees, target v11; never merge or post comments.
- 07e and 07d are web canon; native page 05 is reference only.
- In-app QR scanning, no loopback payloads; server-issued codes work once.
- All locales, token dark mode, 390/768/1280 responsive layouts.
- Preserve CSRF, authorization, explicit confirmation and error recovery.

## Tasks

- [ ] Setup builder: inspect wizard + add-display; write failing flow tests, observe red, implement Welcome/progress/connection/review and responsive kit composition; preserve no-starter-pages behavior and existing-board recognition. Test Home no-displays entry and two-step add-display.
- [ ] Auth builder: write failing activate state tests and reset-password tests, observe red; implement Figma consent/results and H17 reset flow; preserve sign-in redirects and focus behavior.
- [ ] Primary: write failing sessions and QR tests, observe red; add mobile/approver fields, grouped rows, cascade confirmation, pairing create/poll/cancel, loopback warning, address select, connected/revoke and expiration states.
- [ ] Integrate builder commits; merge locale additions by namespace. Add coverage thresholds and changeset.
- [ ] Run full unit coverage, typecheck, lint, formatting, production build; Playwright flow + axe with one worker/spec; capture six breakpoint/theme screenshots and key states.
- [ ] Open PR into v11, get Astra review (maximum three rounds), fix findings and confirm READY at exact head. Poll CI to green unless the wrap-up flag arrives.

## Review focus

- Pending async creation/polls after closing must not leave a usable hidden offer.
- Renewing codes must discard old requests/countdowns; failed requests are retryable.
- A phone revoke names its outcome and preserves TVs when cascade is unchecked.
- Setup must not duplicate a recognized board or promise starter pages.
- Reset tokens/passwords must not leak to URLs, storage or diagnostics.
