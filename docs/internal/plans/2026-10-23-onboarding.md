# First-time onboarding improvements

## Audit and design

The first-time journey should explain FiestaBoard's vocabulary and end with a
clear action: create a page for the display. Keep the existing four steps and
the installed UI components. A copy-only pass would leave lost selections and
false success states; a new wizard architecture would add migration risk without
addressing those problems more directly.

Observed issues:

- Integrations save only when the optional welcome message is sent. Finishing
  without sending discards selections, despite an already-successful summary.
- Integration errors are logged only; retries mark failed work as saved.
- Countdown is built in but is installed through the registry path.
- Optional integrations are advertised as immediately usable without setup,
  including weather and WiFi, which require user configuration.
- Timezone defaults to Los Angeles for every user.
- Quiet hours are described as a sent, queued message, although the API refuses it.
- The final action leads to the dashboard without teaching pages or scheduling.
- TV setup displays a plain URL, and board appearance changes after a successful
  connection test are not saved or marked unsaved.

## Implementation

- [x] Add regression coverage for finishing without a test message, partial
  integration failures and retry, built-in Countdown, quiet hours, and edits
  after a successful board save.
- [x] Separate saving integrations from sending a test message. Preserve successful
  work on retry, check installed plugins, report failures, and offer an explicit
  way to continue and configure remaining integrations later.
- [x] Explain displays, pages, integrations and schedules in translatable copy;
  detect browser timezone; add a create-page completion action and a TV link.
- [x] Run focused wizard tests, type checking, lint and review the final diff.

Constraints: no new dependencies, no changes to credentials storage, retain all
display paths and the preview-only escape route. New keys are present in all 14 locale catalogs with English
defaults;
translations of the new copy need editorial work.

Review focus: retries after partial success, finishing during an active request,
existing installations, welcome-message failure independent of saving, and
navigation after skipping hardware setup. Physical hardware cannot be verified
without a connected display.

## Review and validation

An independent code review found no critical or important regressions. Added
coverage for the create-page handoff and existing integrations following review.
The original regressions failed before the implementation and pass afterward.
The final frontend suite passes: 216 files, 2,525 tests passed and 7 skipped.
TypeScript, changed-file ESLint, frontend formatting, Markdown lint, docs contract,
front matter, and diff whitespace checks pass.
The browser preview could not run: the sandbox refuses Chromium startup, and
computer-use reports no connected browsers. Physical display verification and
translations of new English copy remain follow-up work.

The README now follows the same choose-display → optional-integrations →
create-page journey and documents the preview-only path.
