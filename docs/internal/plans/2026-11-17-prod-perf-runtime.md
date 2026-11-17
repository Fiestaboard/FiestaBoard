# Published v11 runtime performance implementation plan

> **For agentic workers:** Use subagent-driven-development and test-driven-development. Builders own disjoint files in separate existing task worktrees. The root serializes all test/build/browser commands and runtime resources; builders request test execution before implementing the tested behavior.

**Goal:** Make the accepted synthetic API, browser and actual two-hour soak protocols executable, retain failures and raw observations, and derive enforcing budgets only from measured repeated distributions.

**Architecture:** Python standard-library clients seed and verify one fresh authenticated published-image hub, collect endpoint samples and pace a continuous soak. A separate Node/Playwright runner observes the same fixture with an official pinned web-vitals collector. Offline reducers validate completeness and summarize matching strata; no product runtime code or release workflow is changed.

**Tech stack:** Python 3.9+ standard library; existing Playwright; proposed web-vitals 5.1.0 attribution build with verified package integrity and content hash; existing shared Docker roles and one published hub.

**Spec:** Program `status/prodPerf-evidence/c1-runtime-protocol.md` at SHA256 `5b2db0a57ce7526498052a23c7aead055b357c299f7aa5877a7ceba2dcb25b2e`, read with the API/soak and web/bundle audits and `reviews/PROD-prodPerf-protocol-c1-astra.md`. These are source-backed proposals; live failures must correct the harness/protocol before any acceptance claim.

## Global constraints

- Preserve published alpha.3 source `83236253aa8103db856b7efa456e088b9c9ec548` and immutable image pins. Native arm64 runtime is a distinct sample from the amd64 bundle. Never substitute the mutable channel or candidate build.
- BUS 2026-11-17 10:22 removes predecessor waits: only one active PROD job may use the hub. Fresh RUNNING plus actual container inventory is mandatory. At most three total containers; no other job's resources may be stopped or removed. Request a coordinated free role slot if needed.
- No host application server or dependency install. Explicitly documented offline standard-library utilities may run locally. All other execution uses existing shared containers, with task code under their mounted `/worktrees/cx-prodPerf*` paths, never their other-task `/work` paths.
- Root alone executes tests/builds or grants an exclusive command slot. No concurrent suites. Browser uses one worker and one route/profile batch at a time; acquire its lease only while running and release between batches.
- No real data or credentials. A fresh complete synthetic store and ownership marker precede setup. Never reset an existing account/store. Secrets stay in a mode-0600 private file excluded from Git; never enter evidence, argv, logs or reports.
- Fixture: 96 pages, 12 collections, 32 schedules, four geometries and one panel. Read every created object back. Real browser cookie authentication covers internal and v1 endpoints. A stored selection is not proof of a successful send.
- No guessed numeric latency/memory budget. Preserve errors, failed semantics, timeouts, load contamination, missing metrics, sample gaps, image/browser/host/auth/cache metadata and actual phase times.
- Soak is 7,200 real monotonic seconds: 600 warmup, 6,000 activity, 600 drain. Planned ten slots per ten-second cycle, one request in flight, no catch-up bursts; count actual completed operations. A gap or interrupted phase cannot be declared a completed soak.
- Python RSS is not heap. Published live heap and internal queues remain unavailable unless explicitly instrumented as a different experiment. No field Web Vitals or multi-day equivalence claim.
- Every source commit uses `Co-Authored-By: Claude <noreply@anthropic.com>`. No merges of PRs, publication, force pushes, comments, VRT approval or Figma writes.

## Review focus

1. Wrong/nonempty store or existing account must fail before any mutation; seeded-name prefixes alone do not establish isolation.
2. Fast errors and HTTP-200 semantic failures must not improve latency percentiles or disappear from raw records.
3. Dropped arrivals, clock gaps or PID reuse must make soak incompleteness/restarts explicit, not resemble stable memory.
4. Browser metrics must belong to the correct document and verified trusted-input script; missing final callbacks are missing, never fabricated zero.
5. Credentials and session cookies must never leak through request, response, exception or report serialization.

## Shared manifest and record interfaces

The public seed manifest has `schema_version:1`, `fixture:"published-alpha3-96-12-32"`, `seed_id`, `created_utc`, `source_commit`, `base_url`, `boards`, `pages`, `collections`, `schedules` and `verification`.

`boards` is a map keyed by `flagship`, `note`, `array`, `panel`. Each value has `id`, `name`, `rows`, `cols`, `device_type`, `page_ids` (24 IDs). `pages` is a list with `id`, `name`, `geometry` (one map key), `kind`, `revision` and authorable fixture fields. Collections have `id`, `geometry`, `mode`, `page_ids`; schedules have `id`, `board_id` and source-defined recurrence fields. Preserve actual IDs and response fixtures. Private credentials are a separate JSON file with `username` and `password`; browser contexts obtain real cookies, never invented tokens.

JSONL records include `schema_version:1`, `run_id`, `record_type`, `utc`, and monotonic elapsed time. Request records additionally include phase, operation/stratum, geometry, cache/auth labels, elapsed milliseconds, HTTP status, bytes, semantic success/error, and sanitized synthetic request/response. Metadata/phase/error/gap/resource/browser metric records remain separately typed. Write and flush each observation; preserve partial files after failure.

## Task 1: Authenticated seed and API measurement utilities

**Owner:** API builder, separate `cx-prodPerf-api` checkout. **Files:** new `scripts/perf/runtime_common.py`, `runtime_seed.py`, `runtime_api.py`, `test_runtime_api.py`. Do not edit existing bundle files or workflow.

**Interfaces:** `JsonClient(base_url, credentials)` construction performs no network request or authentication. Before any setup/login mutation, root records a read-only pre-start inventory proving the entire synthetic data directory was empty, binds it to the seed ID, absolute mounted path, container identity, image digest, source and origin, and the seeder validates that ownership attestation plus public auth status. Protected content APIs return 409 before setup, so they cannot prove initial emptiness. Explicit setup then checks the exact source-defined bootstrap state before fixture mutations. `seed(client, ownership, out_dir) -> manifest` fails closed on missing or mismatched attestation and exact read-back contracts. `sample_api(client, manifest, out_dir, batches, samples, warmups)` emits raw per-stratum JSONL and a summary with nearest-rank quantiles. CLI programs consume explicit base URL, ownership marker, private credentials path, public manifest path and output directory.

- [ ] Author tests first: reject existing account before writes; reject wrong counts/IDs/geometry; reject batch200 with unavailable items; nearest-rank p95 of1..200 is190; an extra fast401 invalidates success rather than lowering p95; redact password/Set-Cookie/cookie values from all retained errors.
- [ ] Request root's test command execution and preserve genuine RED behavior, not only an import error.
- [ ] Implement exact alpha.3 payloads and seed order from the accepted protocol, with returned panel dimensions, all-board schedule query, revision updates and explicit virtual-send outcomes. Keep collection dry-run calibration variable-only; the bounded rotating diagnostics stay separate.
- [ ] Use one real session per same-origin measurement batch, with its cookie copied only in memory into fresh contexts. Source limits active sessions to 200; logout retains revoked rows and cleanup removes expired rows only. Check the actual session count and current expiry outside timers; require expiry beyond the full batch plus margin. A 401 aborts the batch without retry or silent login. Record any between-batch refresh and session-store growth.
- [ ] Root runs focused utilities and meaningful negative controls; builder fixes demonstrated failures and commits the independently reviewable task.
- [ ] Live smoke on the reserved pinned hub must establish all fixtures and semantics before timing. Three separate batches of200 successful samples after20 warmups per declared endpoint/geometry/auth/cache stratum; retain errors and drift separately. No silent retry.

## Task 2: Soak pacing, Linux telemetry and offline reports

**Owner:** API builder after Task1 interface is stable. **Files:** new `scripts/perf/runtime_soak.py`, `runtime_collect.py`, `runtime_report.py`, `test_runtime_soak.py`, `test_runtime_report.py`.

**Interfaces:** pacing produces one scheduled slot at a time from real monotonic deadlines and emits missed slots instead of accumulating work. Collector runs inside the existing hub, reads Linux proc/cgroup/data-store metrics, and emits JSONL every5s with PID plus start identity. Reducer accepts saved raw files and metadata, never starts services, and returns completeness, actual counts/factors, endpoint quantiles and resource block summaries.

- [ ] Test first: overrun drops missed slots/no burst; altered phase duration or missing tail fails7200s completeness; PID reuse is a restart; absent heap/queue metric stays unavailable; timeout remains censored; partial JSONL and failed samples survive reporting; strata are never pooled accidentally.
- [ ] Request root's RED run, implement minimal logic, then request GREEN and negative-control checks.
- [ ] Implement the ten-operation cycle from the protocol; changed-save/send ring is12 compatible literal pages. Use real revisions, explicit frame/send checks and declared collection cadence; restore state outside timed windows. Record actual override/silence subscenario transitions separately.
- [ ] Record RSS/PSS, thread/FD/socket/disk/cache counts and cgroup metrics where available, process restarts, collector gaps and unavailable fields. Do not force GC or invent queue/heap counters.
- [ ] Root validates a short diagnostic run (never called a soak pass), then executes the actual600/6000/600 window under fresh resource exclusion. Preserve every sample and interruption.
- [ ] Root derives and reviews explicit per-profile budgets from repeated observations and controlled negative controls. Add enforcing CI only after matching-runner calibration; mismatch/missing evidence fails closed. Do not lift thresholds automatically.

## Task 3: Browser performance runner

**Owner:** browser builder, separate `cx-prodPerf-web` checkout. **Files:** new `scripts/perf/web_protocol.mjs`, `web_run.mjs`, `test_web_protocol.mjs`, and browser reproduction documentation under `scripts/perf/`. No product UI or package/lockfile edits.

**Interfaces:** runner consumes public manifest, private credentials file, pinned collector bundle/metadata, target nginx URL and output directory. It uses the existing Playwright dependency resolved from this checkout's web package. Profiles, cache state, route, geometry, batch/sample numbers and actual tool/environment identity are explicit CLI/config inputs.

- [ ] Author pure utility/transport tests first: exact network byte conversions; final metrics keyed by document/ID; absent final callback fails completeness; secret redaction; relay forwards synthetic body/status/content encoding without caching or API mocks. Ask root to run RED before implementation, then GREEN afterward.
- [ ] Use a transparent loopback HTTP relay within the browser runner's container when needed to expose the same published nginx to Chromium's real localhost secure context. Use raw Node HTTP streams, preserving compressed body bytes, status, duplicate Set-Cookie headers and cache directives. Preserve relative redirects; rebase only redirects to the exact upstream origin onto the stable relay origin. Reject external measurement navigation before following it. Record this additional hop and validate its overhead separately. Do not grant insecure origins secure status with a browser flag. No fourth container, TLS sidecar or host server. Parent must validate the transport/lifecycle before samples.
- [ ] Desktop1440×900/DPR1/CPU1×/20ms/20Mbit down/10Mbit up; phone390×844/DPR3/touch/CPU4×/150ms/1.6Mbit down/0.75Mbit up. Pin Chromium, mode and UA. Validate actual secure context and SW state for every cache stratum.
- [ ] Inject a verified local web-vitals5.1.0 attribution bundle and binding before app scripts. Retain intermediate/final LCP and scripted INP, document IDs, raw event diagnostics, route-ready timing and errors. No CDN in a timed page.
- [ ] Use the protocol's exact ready assertions and trusted click/tap/keyboard actions; fail missing actions instead of optional skips. Verify actual hidden-page flush via a second foreground tab while sink remains alive. Missing/unsupported metrics are explicit, not zero.
- [ ] Warm and cold cache runs share the same declared transport, auth semantics and profiles. Keep one real cookie session per same-origin batch and inject it in memory into fresh contexts. Validate current session count and expiry outside timers; never login per sample or export cookies. Abort on 401. The source-backed auth amendment in program status/prodPerf-evidence/c1-runtime-auth-amendment.md must pass review before live use.
- [ ] Execute one diagnostic route/profile first. Root then runs serial batches, at least20 recorded samples per declared route/profile/cache stratum after separate warmup, with repetitions before numeric gates. Preserve all failures and traces; no field/native-phone claim.

## Task 4: Integration, evidence and CI

**Owner:** root, with independent Astra review in `cx-prodPerf-review`. **Files:** existing performance docs/plan/changeset, private-output ignore rule, budget/evidence summaries, additive performance CI after validated calibration.

- [ ] Reconcile concrete live failures with the protocol and obtain scoped independent review before trusting a runner.
- [ ] Keep owned raw evidence on ExtHD, record actual hardware/load/image/browser/auth/cache metadata and limitations. Do not add private data or large raw runs/tarballs to Git.
- [ ] Run required local checks serially in shared roles after integration; existing application checks remain intact. Track exact-head hosted checks separately, including actual merge source and retained artifacts.
- [ ] Review calibrated budgets and negative controls independently; source READY cannot replace observed runtime acceptance.
- [ ] Run the real two-hour window, report actual wall time, phase gaps, counts, memory/resource changes and missing instrumentation. Interrupted runs remain incomplete.
- [ ] Normally push the integrated exact head, obtain Astra READY at that head, observe green CI, and update program status/review/ownership. Keep owner Fable/merge/publication separate. Check WRAPUP before each new step; if set, finish current step and record precise resumption.

## Initial rulings and checks

The user opted out of questions and explicitly authorized autonomous subagents, so no design/plan approval pause is inserted. Concurrent source implementation is allowed only in the two disjoint named worktrees/files, overriding the skill's general sequential-builder preference; execution of tests and resources stays serialized. Existing linked worktrees were inspected clean before reuse; no primary tree is touched. The current3shared containers are idle but a hub slot has not been released, so harness preparation proceeds without retiring a pre-existing container. Jev selected that path at0.61; it is not authority to stop another job's resources.
