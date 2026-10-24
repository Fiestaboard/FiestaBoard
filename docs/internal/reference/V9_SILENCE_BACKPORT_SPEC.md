# Stable silence backport (#1943, #1944)

Prepare a local review candidate on stable v9. The existing behavior on `next`,
merged in #2257, is the reference contract, not a patch to cherry-pick wholesale.
The user authorized finishing leftover work, explicitly deferred #2323, and
asked for a tested local candidate before any push or PR. No release, deploy,
live-board changes, dependency upgrades, or deprecated endpoint removal.

## Behavior

- Silence holds manual page selections and blocks hardware writes from live
  editing and every manual send surface unless the caller explicitly supplies
  `override_silence=true`. Existing v1 `force` still only forces unchanged
  content; it is not permission to bypass silence or pause.
- Pause always prevents writes, including explicit silence overrides and queue
  delivery. Page choices may still persist while paused. UI-only installs and
  per-board geometry retain existing stable semantics.
- `show_queued_on_exit` is an optional boolean (default false), install-wide
  with per-board overrides. Omitted settings updates preserve its saved value.
- When holding is enabled, accepted manual sends persist a typed intent, one
  per resolved board id, newest wins. Intents cover text, lines, raw grids,
  saved pages and plugin displays. Deliver fresh page/display content, wrap
  text using the v9 renderer, expire after 24 hours, and discard only after
  successful delivery. Retry after offline, throttled or paused attempts;
  restarting during silence must not lose the message.
- Automatic retry also applies after an interrupted or ambiguous delivery;
  a physical send can therefore repeat after restart or failed cleanup. Do not
  promise exactly-once delivery or require manual recovery for uncertainty.
- An existing queue that cannot be read or decoded is not an empty queue.
  Preserve its contents, expose the failure, and reject new acceptance/discard
  rather than overwriting recoverable data. A genuinely missing file is empty.
- Held HTTP message sends return 202 and held=true; unaccepted silenced sends
  retain their refusal contract. Selection/live-preview responses can report
  silenced without pretending a board write occurred. No false sent=true.
- Explicit successful writes supersede an older held intent for that board.
  Failed or paused writes must not lose the held intent.
- Completion of an older in-flight delivery must not discard a newer intent
  queued for the same board while that delivery was running.
- GET /silence-status adds ends_at_utc, holds_blocked_sends and nullable held
  {kind, preview, queued_at}. DELETE /silence-queue?board_id=... discards only
  that resolved board's intent; unknown write targets return 404.
- Status also reports queue_available=false with held=null when persisted queue
  data is unreadable; timing remains valid, and Home shows an unavailable warning.
- Home shows silence throughout the window, its ending time, the saved page
  or held-message preview, Show now and Discard actions. Page selection says
  it is saved for later. Force Set, Compose and Live Output warn before an
  explicit wake. Settings exposes the opt-in toggle. Hide misleading
  out-of-sync warnings during silence. Preserve all 14 locales and motion,
  keyboard and accessibility conventions using installed @fiestaboard/ui.

## Compatibility and verification

Adapt to v9's board clients, rendering and temporary-override engine; do not
import output-driver or canvas architecture from v10. No package changes.
All dependency installation and application/tests run in isolated Docker
containers. Never use live configuration or credentials. Tests target fake
hardware and temporary data. Preserve the dirty original checkout.

Prove RED then GREEN for settings/store/policy, each send surface, engine
delivery and UI controls. Include target-board isolation, midnight boundaries,
restart/expiry/retry, pause, invalid requests, discard and successful override.
Run focused suites after changes, then full Python and web suites, typecheck,
production build, scoped lint/format and route-contract checks. Record exact
commands, outcomes and any baseline failures. Finish with independent review.
