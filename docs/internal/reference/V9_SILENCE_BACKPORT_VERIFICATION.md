# Stable/v9 silence backport verification

Date: 2026-10-24. Issues: #1943 and #1944.
Branch: `fix/v9-silence-backport`.
Worktree: `/tmp/fiestaboard-v9-silence-backport`.
Stable base: `256c9d58d2d13a58cc50429574a06982312b22ea`.
Reviewed implementation: `80923fb3335ef992616f22f6539371cbc7849154`.
Prior tested implementation: `226a8a73c1ca7d996f39c73d826a6c938c60f75a`.
Task 4 corrects retry and unreadable-store behavior; its verification is recorded below.

## Result

The local candidate implements persisted per-board held intentions, 24-hour
expiry, explicit silence overrides, truthful send responses, pause/output gates,
retry/restart handling, and the stable engine and UI controls. Invalid requests
preserve accepted intentions; successful older writes preserve newer concurrent
holds. Unrenderable holds allow normal content and explicit override recovery.
Home keeps pending-message preview and Discard visible after quiet hours end.
All 14 locales, user guidance and generated API documentation are updated.
No v10 output architecture or dependency changes were introduced.

Task 1, Task 2 and Task 3 independent reviews approved their earlier changes.
The whole-branch review found four Important issues; one grouped fix wave
addresses all four in the tested implementation above. Bounded final re-review
approved all four as addressed at that time. Task 4 supersedes the earlier
delivery-marker policy. Fresh final independent source review approved the
complete correction and its interactions with no actionable findings. No merge
or publication approval is implied.

## Prior candidate verification

| Gate | Result |
| --- | --- |
| Full Python on final send/store/engine logic | 9468 passed, 1 existing skip; 219 existing warnings; 166.47 seconds |
| Subsequent response-metadata/schema checks | 328 passed, including 3 new OpenAPI assertions; 5.68 seconds |
| Full exact-lock web | 190 files; 2267 passed, 7 existing skips; 159.89 seconds |
| Final covering backend/contract and UI | 1250 backend passes; 82 UI passes; additional in-flight fix covered by 160 passes |
| Static/build | Ruff, Python format, TypeScript, production SPA build, scoped ESLint/Prettier clean |
| Docs/locales | 41 frontmatter pages; 41 pages/5 categories; final record included in 86 Markdown files/zero issues; feature spelling clean; all 14 catalogs/placeholder checks pass |
| Generated API | Current, 2023 lines; one added v1 active-page 503 row |
| Actual API with mock board | Five groups: held202/no wire; pause blocks override/preserves hold; explicit override writes/clears; quiet-exit delivery; held summary |
| Production browser with actual API/mock board | Eight groups: Discard/no wire; explicit Show now/write; paused no write/preserve; inactive+paused pending preview/Discard; four desktop/mobile/light/dark overflow and scoped axe checks |

The full Python result precedes only three response declarations and their
three new metadata tests. No send logic changed afterward; the 328-test schema
and contract gate verifies that final metadata. Final HTTP/browser checks used
the reloaded final backend and final production UI build. All final gates exited
0. Browser page errors were empty. The pending mobile dark capture was visually
checked: readable text and fitting controls without clipping.

All application, dependencies and tests ran inside Docker. Python used
`fb-mcp-pytest:latest`, `--network none`, and a deterministic example.com hosts
entry solely for SSRF checks before mocked fetches. Web used Node24 with the
unchanged stable lockfile and dedicated dependency volume
`v9-silence-web-node-modules-20261024`; full tests used `--maxWorkers=2`.
Heavy checks ran sequentially. The single Python skip requires an xdist worker;
the seven web skips predate the candidate. No assertion or timeout was weakened.
Initial DNS/thread failures were reproduced on unchanged base. Earlier web
resource-limited runs and a stale browser fixture are retained and attributed.

## Evidence and reproducibility

Exact Docker prefixes, RED/GREEN commands, outputs and chronology are recorded
in the local ignored workspace
`.superpowers/sdd/2026-10-24-v9-silence-backport/`:

- `task-1-report.md`, `task-2-report.md`, `task-3-report.md` and their scoped reviews.
- `whole-branch-review.md`, `final-fix-report.md`, and the final bounded re-review.
- `evidence/final-fix-full-python-corrected.log`,
  `evidence/final-fix-metadata-contracts.log`, `evidence/final-fix-full-web.log`.
- `evidence/final-fix-type-build-lint.log`, `evidence/final-fix-docs.log`.
- `evidence/v9-silence-final-record-docs.log` verifies the completed plan and
  this internal record; no application source changed after final review.
- `evidence/v9-silence-real-api-final.log`,
  `evidence/v9-silence-real-browser-final.log`, `evidence/real-*.png`.
- `real-api-setup.mjs` and `real-browser.mjs` preserve the synthetic integration
  harness. They require an isolated mock-board/backend network, never live data.

The first whole-branch full run passed 9467 tests before a newly proven in-flight
marker-ordering race was corrected. The final 9468-pass run supersedes it.
The final fix adds 29 Python behavioral tests, 3 metadata tests and 6 web tests.

## Task 4 automatic-retry correction

The local candidate now retries after both ordinary restart and ambiguous
delivery, and preserves unreadable queue files without acknowledging new
acceptance. The earlier marker policy is superseded. Home exposes unavailable
storage while retaining valid silence timing. Seventeen new reliability cases
cover damaged files, repair, legacy marker compatibility, retry concurrency,
paused/UI-only results and invalid-selection precedence. Earlier marker tests
were updated to assert automatic retry rather than deleted.

| Gate | Task 4 result |
| --- | --- |
| Backend RED | 30 failed, 35 passed before implementation; subsequent no-write compatibility matrix: 8 failed |
| UI RED | Unavailable warning: 1 failed, 5 passed before implementation |
| Covering backend | 1328 passed; subsequent final route correction: 324 passed |
| Final full Python | 9488 passed, 1 existing xdist-only skip, 219 warnings; 170.20 seconds |
| Full web, maxWorkers=2 | 190 files; 2267 passed, 7 existing skips; 159.76 seconds |
| Covering UI/locales | 79 passed across 4 files |
| Static/build | Typecheck, production SPA build, scoped ESLint/Prettier, Ruff and Python format passed |
| Locale scope | All 14 catalogs: exactly two recovery keys replaced with two unavailable keys; all other values unchanged |
| Generated API | Current, 2023 lines; schema, convention and response golden tests passed |
| Docs | 41 frontmatter pages, 41 pages/5 categories, 86 Markdown files without issues, feature spelling clean |
| Actual HTTP/mock board | Five groups passed on the final reloaded source |
| Production UI/actual API | Eight groups passed, including inactive paused pending-message Discard/no wire and four viewport/theme checks |
| Damaged synthetic queue | Five groups passed: status unavailable, hold/discard 503, no wire, four viewport/theme warning checks; exact damaged bytes preserved |
| Repair without restart | Six groups passed: available status/exact pending preview, four viewport/theme checks, actual UI Discard/no wire |
| Fresh final source review | Approved; no Critical, Important or Minor findings |

The first Task 4 full Python run passed 9480 before self-review found the
no-write compatibility interaction; its log is retained and the 9488 result
supersedes it. The web source was unchanged by that backend correction.
Raw logs and exact commands are retained in the ignored task workspace's
`task-4-report.md`, `task-4-controller-evidence.md`, `task-4-review.md`,
`evidence/task-4-*.log` and `evidence/v9-silence-task4-*.log`. All final browser
page-error arrays are empty; scoped axe and overflow checks passed. The mobile
unavailable warning was visually inspected and is readable without clipping.
The reused fresh-container harness initially ran before service readiness and
assumed a ten-second deadline below its configured fifteen-second polling
interval. Final readiness is explicit, and the deadline derives from the
configured poll plus ten seconds (25 seconds in the passing log). Earlier
failures and their source-derived explanation are retained; no product latency
change or semantic assertion relaxation was made. No publication is authorized.

## Current reliability decisions and limits

Durable queue mutations publish memory only after persistence succeeds.
Automatic retry applies to ordinary restart and ambiguous delivery, matching
the established v10 contract. An acknowledgment or cleanup failure may repeat
a physical send; delivery is not exactly once. Successful I/O remains truthfully
sent even if cleanup fails. A physical write and filesystem commit cannot be atomic.
Unreadable or malformed queue data is preserved and exposed as unavailable;
mutations fail until repair, and status checks retry loading automatically.
An already in-flight hardware write cannot be undone by Discard.

The stock shipped Docker/Pi configuration uses one Python writer. This is a
deployment convention, not enforcement: external Home Assistant wrappers,
custom conf.d programs or multiple containers sharing data were not verified.
Setup welcome retains its silence/pause guards. Legacy REST debug blank/fill/info
still bypass silence while respecting pause/output; canonical/MCP equivalents
check silence. Temporary-override creation retains its explicit wake semantics,
while engine pause still prevents hardware I/O. No
physical board, native screen reader, all-language native editorial review or
whole-application WCAG audit was performed. Isolated fake hardware, viewport
layout, scoped axe and locale completeness were verified.

Automatic approval review denied the reviewer's named
`v9-silence-final-review-probes` Docker diagnostic before execution, citing the
earlier screen-only scope. Later implementation/testing authorization was
forwarded; that diagnostic was not retried or rerouted. Source review completed,
and the authorized implementation regression suites above ran successfully.
No pending or uncertain action remains from that diagnostic.

The original dirty checkout was untouched. No push, PR, merge, release, deploy,
live-board setting change, deprecated endpoint removal or #2323 work occurred.
Docs/website/dependency publication remains separate. The worktree and local
branch are preserved for review.

## Rulings I made

- Execute the authorized local plan without another approval pause. Cost if
  wrong: reversible local rework.
- Use conditional discard to preserve a newer hold during an older delivery.
  Cost if wrong: small additional store API complexity.
- Snapshot fresh normal content through a bounded read-only helper instead of
  refactoring the v9 pipeline. Cost if wrong: extra rendering or selection drift.
- Keep engineering plans internal and preserve the evidence workspace identity.
  Cost if wrong: internal reference paths change.
- Retain the existing single-process storage boundary. Cost if wrong:
  independent concurrent writers can lose queue updates.
- Retain existing setup guards, diagnostic exceptions and temporary-override authorization;
  fix their new held-intent interactions. Cost if wrong: existing policy
  exceptions remain.
- Retry ambiguous delivery automatically, retaining conditional cleanup and
  explicit persistence errors. Cost: a physical send can repeat after an
  ambiguous outcome or cleanup failure. No exactly-once claim is made.
