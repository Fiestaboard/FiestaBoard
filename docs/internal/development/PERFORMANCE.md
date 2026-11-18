# Production performance evidence

The bundle gate measures the static client files in the production image already
built for E2E. It does not rebuild the web app or add a container. It runs after
the browser tests, fails the existing E2E job on an exceeded limit, and retains
the JSON report on failure. Existing release and publishing workflows are
unchanged.

## Observed published bundle

The baseline is `fiestaboard/fiestaboard:v11-alpha-11.0.0-alpha.10`, measured
on 2026-11-18 with `scripts/perf/fetch_published_client.py` (see
"Re-baselining" below). That tag resolved to index
`sha256:a5e24ae550002db07513b27cfd56d201e4158c78b0ff325b9cf58f7c49c8f649`.
The measured platform is **linux/amd64**, with manifest
`sha256:b56e719de340afe880a35dcff6de9125dd9dcf27997931401ae357fc64392d6f` and
config `sha256:b2e7841ef43493e4f88e3da1365b208d76cd50ffc61efb3049aa87712a19b2a3`.
Its environment records `VERSION=11.0.0-alpha.10`. The
[source tag](https://github.com/Fiestaboard/FiestaBoard/tree/v11.0.0-alpha.10)
and successful
[release run](https://github.com/Fiestaboard/FiestaBoard/actions/runs/44276902049)
identify `bf914c0ea649ff0eaeb5551ecae711f7176ba524`. The image has no
source-revision label; this is corroboration, not a source attestation.

Every layer was downloaded over the public Registry HTTPS API without executing
the image, and its compressed digest, size and uncompressed diff ID were verified.
Only regular files under `app/web/build/client` were replayed, in layer order:
the client COPY layer (zero-based 18) writes all 586 client files and layer 30
repeats them with identical bytes. A link, device or whiteout touching that tree
would have stopped the run. The committed
[sample](../../../scripts/perf/published-v11-alpha10.json) records every path,
size and hash, plus the registry provenance.

| Metric | Observed raw bytes | CI ceiling |
| --- | ---: | ---: |
| All JavaScript, 279 files | 7,457,365 | 8,203,264 |
| All CSS, 2 files | 282,521 | 311,296 |
| Fonts, 5 files | 138,068 | 152,576 |
| Largest JavaScript file | 573,266 | 630,784 |

There is **one unique published artifact sample**, not repeated timing samples.
It includes lazy route and locale chunks and the service worker. These totals
are not the initial payload of any route. The inventory also records 272 source
maps (22,837,120 raw bytes) as image-storage cost; nginx refuses `.map` requests,
so maps do not count toward served-code ceilings. Other assets are inventoried
but not currently budgeted.

The first baseline was `11.0.0-alpha.3` (JS 6,421,698 / CSS 255,096 bytes).
It was replaced with alpha.10 after web slices 2.5, 2.9–2.11 and 2.14 shipped:
measured against alpha.3, v11 had reached 99% of the JS and 99.98% of the CSS
allowance, so the gate would have failed every later PR regardless of its content.

Per-file gzip level 6 estimates total 2,362,574 JavaScript bytes and 45,081 CSS
bytes. These are estimates, not observed wire transfers; nginx filtering,
headers, cache/service-worker state and transport overhead are unmeasured.
Only raw bytes gate, avoiding compressor-version differences. The inventory
records Python and zlib versions.

Each ceiling is the measured raw value multiplied by 1.10 and rounded up to
1 KiB. This explicit 10% growth allowance catches large additions without
requiring identical chunks. It is a policy choice, **not** a statistically
calibrated latency budget or an assertion that the current bundle is fast.
Do not raise limits automatically after a failure: inspect the file report and
justify the cost in review. No arm64 equivalence has been measured.

## Reproduction

The two scripts are offline standard-library utilities explicitly supported
for local execution; they do not install dependencies or start services:

```sh
python3 -m unittest discover -s scripts/perf -p 'test_*.py' -v
python3 scripts/perf/bundle_budget.py \
  --client /path/to/copied/web/build/client \
  --budget scripts/perf/bundle-budget.json \
  --report /path/to/bundle-report.json
```

Use a copy from the exact production image under test, not a development
directory. Record the image digest and source revision beside the report.
The utility refuses missing/empty HTML, JavaScript or CSS, symlinks, and
unreadable subdirectories, and malformed limits. Exit 0 means the raw-byte limits passed; 1 means an exceeded
limit (report still written); 2 means invalid input. Gzip and file hashes remain
diagnostic. Hosted `bundle-measurement` artifacts are retained for 30 days.

## Re-baselining on a newer published alpha

The baseline is always a **published** image, never a branch build. Move it
forward when shipped features have used up the allowance (each alpha legitimately
grows the bundle), not to let one PR through. Re-baselining applies the same
110%-rounded-to-1 KiB rule to the new published sizes; it never adds extra
headroom, and limits are never edited by hand.

1. Pick the newest published, immutable alpha tag, for example
   `v11-alpha-11.0.0-alpha.10`, and confirm its release run succeeded.
2. Copy its served client out of the registry into an empty scratch directory
   (Python 3.11+; standard library only).
   The script verifies every layer digest and diff ID, replays only regular
   files under `app/web/build/client` in layer order, fails closed on links or
   whiteouts that touch that tree, and never runs the image or uses Docker:

   ```sh
   python3 scripts/perf/fetch_published_client.py \
     --tag v11-alpha-11.0.0-alpha.10 --out /path/to/scratch/alpha10
   ```

3. Measure it and rewrite the committed sample and limits. The script refuses an
   image whose `VERSION` environment does not match `--version`:

   ```sh
   python3 scripts/perf/rebaseline_bundle.py \
     --fetched /path/to/scratch/alpha10 --version 11.0.0-alpha.10
   ```

   This writes `scripts/perf/published-v11-alpha10.json` (every path, size and
   hash plus registry provenance) and points `bundle-budget.json` at it. Delete
   the superseded sample in the same PR.
4. Update the table under "Observed published bundle" with the new tag,
   digests, measured values and ceilings, run the unit tests, and open the
   re-baseline as its own reviewed PR.

## Runtime gates still open

No API p95 baseline, LCP, INP, or memory-soak result is established by this PR.
The initial artifact extraction used no containers or application suites.
Local process inspection was sandbox-denied. For this campaign, the owner now
accepts fresh dispatcher `codex/RUNNING` evidence plus Docker inventory to verify
PROD exclusion. Shared role containers have since been used for local source
checks; a published runtime hub still requires a free slot within the three-container
cap. Other jobs' resources must not be stopped or removed.

Artifact measurements used macOS 27.2 arm64 and Python 3.9.6; host CPU model
and RAM queries were denied. A contemporaneous load observation was
5.91/3.95/3.38 (1/5/15 minutes). Load does not alter file bytes; it precludes
inferring timing results from this extraction.

Before setting API or browser budgets, use a dedicated synthetic seed and the
immutable published image through nginx, with real authentication and declared
cache states. Preserve every response/status, elapsed sample, semantic failure,
timeout, route/action, profile and environment. Separate endpoint/geometry/auth
strata; do not pool their p95s. Calibrate on repeated runs and retain all raw
samples before choosing enforcing limits. A shared-host or emulated browser
result is a synthetic lab result, never field Web Vitals.

The remaining soak requires an actual two-hour wall-time run with recorded
activity acceleration and realized operation counts. Record process identity,
RSS, available heap telemetry, resources, queues, pauses and drain recovery.
Production is Python plus nginx, with no Node web server. RSS is not Python
heap; live heap and internal queue depths are not currently exposed by the
published image and must be marked unavailable unless separately instrumented.
Do not claim equivalence to a multi-day soak or infer absent leaks from a
shortened test. Detailed source-backed runtime protocols and blockers remain
in the program's `reviews/PROD-prodPerf.md` and its API/browser audit attachments.
