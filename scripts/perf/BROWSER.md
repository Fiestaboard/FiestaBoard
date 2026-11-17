# Published-image browser measurements

The browser runner is under construction. Utility/transport implementation is
awaiting the root's verification; it does not collect a valid sample.
No browser, relay, login, or session is created when modules are
imported. A source review or a green utility suite cannot establish runtime
measurement readiness.

The implementation contract is
[`2026-11-17-prod-perf-runtime.md`](../../docs/internal/plans/2026-11-17-prod-perf-runtime.md),
Task 3, read with the accepted program runtime protocol and its amendments.
The immutable target remains published alpha.3, source
`83236253aa8103db856b7efa456e088b9c9ec548`. Candidate checkout source is not a
replacement production baseline.

## Serialized verification

The root alone runs commands, in the existing shared role, with this checkout
mounted at `/worktrees/cx-prodPerf-web`. No install or application server is
needed for these Node standard-library utility/transport tests:

```sh
node --test /worktrees/cx-prodPerf-web/scripts/perf/test_web_protocol.mjs
```

The transport cases temporarily bind controlled synthetic upstreams and relays
to ephemeral loopback ports inside that role. They do not contact a live hub or
mock application APIs in a measurement. The first run is intentionally RED
against callable stubs. Root must preserve its actual output before the
implementation advances, then run GREEN against the same tests.

## Parent-reviewed transport contract

When a relay is necessary, the measured hop runs inside the existing browser
role and forwards to the target's real published nginx. It binds loopback only;
no fourth container, TLS sidecar, host application server, or insecure-origin
browser flag is permitted. Record both target and loopback origin and calibrate
the additional hop before taking samples.

The relay uses `node:http` or `node:https`, forwarding entity bytes without
decompression/recompression, application API responses, or a relay cache.
Preserve status, content encoding/length, cache headers and separate Set-Cookie
headers. Upstream Host identifies nginx. Strip hop-by-hop headers as required
by HTTP; do not turn an upstream error or failed request into synthetic success.
Retained observations must redact cookies, passwords and authorization values.

Relative Location values remain relative. An absolute redirect to the exact
target origin is rebased to the loopback origin, preserving path,
query and fragment, so browser cookies and secure-context semantics stay on the
declared origin. Foreign redirect locations remain identifiable and forbidden
to the measured browser navigation; they must never be silently relabeled as
the target. The raw transport never follows a redirect. Origin and Referer map
from the exact relay origin to the exact target origin, retaining the Referer
path/query; foreign origins stay foreign. Explicit Domain cookies fail the
batch without a rewrite. Published alpha.3 `_set_session_cookie` supplies no
Domain attribute, so its genuine session cookie is host-only. Parent reviewed
this policy; actual transport/lifecycle calibration remains required before
sampling.

## Authentication amendment

Use one genuine browser login per same-origin batch, outside timers. Copy that
cookie jar in memory into fresh cold-browser contexts. Never emit storage state,
session-cookie values, credentials or raw authentication headers into public
artifacts. Never repeatedly log in per context: published authentication stores
each login in SQLite and has a 200-session cap; logout revokes rather than
immediately removing that row.

Before a batch, read session count and the current session's expiry outside
timing; its validity must exceed the planned batch plus an explicit margin.
Record only count, flags and expiry metadata. A 401 aborts the batch and remains
an error sample. No silent retry, relogin or invented token is allowed. The public
source contract is `GET /api/auth/sessions` returning `sessions` and
`current_session_id`; find that ID's browser row and read its actual offset-aware
`expires_at`. Counts must remain stable after the one login. The root publishes
the source-backed protocol amendment before execution.

## Collection gates

- Pin actual Chromium executable/version, Playwright version, headful display,
  User-Agent, host/load identity and verified web-vitals 5.1.0 attribution bytes.
  A supplied digest is useful only after provenance/package-integrity review.
- Install the out-of-process binding and one initialization script before app
  scripts. Retain intermediate and final metric reports keyed by document ID
  and metric ID; an SPA transition is not a new document metric.
- Assert exact fixture counts, selected board, seeded content and mandatory
  trusted actions. Heading-only readiness and optional action skips fail.
- Verify real secure context and service-worker/cache state per cache stratum.
  Both device profiles share transport and authentication semantics.
- Keep the target and metric sink alive while a second foreground tab makes
  the target genuinely hidden. Missing final callbacks, unsupported metrics or
  unverified trusted input make completeness false; never invent zero values.
- Validate the collector lifecycle against a trace and measure relay/collector
  overhead separately before serial route/profile batches. Preserve failures
  and partial records. Numeric runtime budgets require repeated observations.

No live diagnostic, repeated browser distribution, field Web Vital, native
phone claim, or calibrated runtime budget has been produced by this code.

## Correction to the inherited collector recipe

Use official `webVitals.onLCP` and `webVitals.onINP` with
`reportAllChanges: false` for the primary final metrics. Use separate buffered
LCP and Event Timing observers for intermediate diagnostics; raw event durations
are not INP metrics. This corrects the accepted protocol's earlier `true`
recipe without promoting any intermediate callback to a final value.

In web-vitals 5.1.0, the reporter suppresses unchanged values even when a force
report is requested. With final-only registration, no prior report exists, so
the first official final callback is emitted even for a genuine zero value.
LCP finalizes on the first trusted input or real visibility transition; INP
force-reports when the document becomes hidden. The attribution wrappers pass
these options through. See the versioned
[reporter](https://github.com/GoogleChrome/web-vitals/blob/v5.1.0/src/lib/bindReporter.ts),
[LCP implementation](https://github.com/GoogleChrome/web-vitals/blob/v5.1.0/src/onLCP.ts)
and [INP implementation](https://github.com/GoogleChrome/web-vitals/blob/v5.1.0/src/onINP.ts).

Only the first controlled foreground document lifecycle is admissible. Earlier
hidden state, a BFCache restore, missing trusted input, unsupported APIs, missing
final callbacks or a failed out-of-process sink make the sample incomplete.
Because INP can queue interaction processing through idle/hidden callbacks,
source inspection alone cannot prove every pending entry was drained. A real
Chromium trace with observed trusted events, actual hidden transition and sink
acknowledgements is required for lifecycle calibration before baseline samples.

The collector artifact is the packaged
`dist/web-vitals.attribution.iife.js`, global `webVitals`, from official npm
web-vitals 5.1.0. Its verified content SHA-256 is
`397a8cffdeec35be161d00e3ed1378a644223f710dafee49584d376a64d3b9a0`.
The parent holds npm integrity verification and license provenance separately;
no package or lockfile is modified.

## Bound run evidence

One invocation owns one route/profile/geometry/cache/batch, with serial samples.
Diagnostic mode may execute a small calibration sequence without prior
calibration, but its output is explicitly not a baseline. Standard measurement
requires verified relay and lifecycle calibration evidence.

The seed ownership JSON is shared unchanged with the API builder:
`source_commit`, `image_manifest`, `container_id`, `base_url`, `seed_id`,
`data_dir`, `empty_before_start`, `prestart_entries`, `attested_utc`.
The root captures a separate `run-context.json` from fresh actual inventory:

```json
{
  "schema_version": 1,
  "run_id": "synthetic-run-id",
  "seed_id": "<same synthetic seed ID>",
  "data_dir": "<same fresh synthetic data path>",
  "source_commit": "83236253aa8103db856b7efa456e088b9c9ec548",
  "captured_utc": "<actual UTC>",
  "manifest_sha256": "<hash of public manifest bytes>",
  "ownership_sha256": "<hash of ownership bytes>",
  "target_origin": "<declared published nginx origin>",
  "container": {
    "id": "<actual container ID>",
    "image_id": "<actual image ID>",
    "manifest_digest": "<immutable platform manifest>",
    "architecture": "<actual architecture>"
  },
  "exclusion": {
    "running_ids": [],
    "container_names": [],
    "checked_utc": "<actual inventory UTC>",
    "browser_lease_owner": "<actual lease owner>"
  },
  "host": {
    "os": "<actual OS>",
    "architecture": "<actual architecture>",
    "cpu": null,
    "memory": null,
    "unavailable": []
  },
  "calibration": { "relay_report_path": null, "lifecycle_report_path": null }
}
```

These are evidence bindings, not an approval boolean. File hashes, target
origin, seed/source/image identities, current fixture and freshness must agree
before timing. Browser/tool identity, actual headful display, UA, profile,
service-worker state and authentication/session metadata come from the runner's
actual observations. Unknown host facts stay unavailable. Root has not yet
produced this live inventory context; these examples authorize no execution.

The manifest's internal canonical-content hash is distinct from the root
context's `manifest_sha256`, which binds the actual public manifest file bytes
including that internal field. Compare each hash against its own representation.

## Integrations interaction amendment

The desktop Integrations route needs a trusted action to produce scripted INP.
On the existing enabled Date & Time integration, open **Configure**, assert the
**Date & Time** sheet and loaded configuration, then choose **Cancel** and assert
the sheet closes. Do not toggle, save, sign in, refresh, install or enable a
plugin as this action. The phone performs this same action plus its declared
More-menu script.

Published alpha.3 `web/app/routes/integrations._index.tsx` opens the sheet with
local state and GET queries for plugin details/data/OAuth connection metadata
(lines 1130–1179). Its explicit Save Changes/sign-in handlers invoke the config
update (1196–1223); Cancel is a SheetClose at 1637–1642. Thus open/cancel has no
saved config payload. Retain the actual GET diagnostics, compare Date & Time's
configuration before/after outside timers, and reject any config-write request
during this script. The recipe adds no plugin or provider and must still be
validated on the exact published image before baseline sampling.
