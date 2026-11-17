# Production performance evidence

The bundle gate measures the static client files in the production image already
built for E2E. It does not rebuild the web app or add a container. It runs after
the browser tests, fails the existing E2E job on an exceeded limit, and retains
the JSON report on failure. Existing release and publishing workflows are
unchanged.

## Observed published bundle

On 2026-11-17 the public `fiestaboard/fiestaboard:v11-alpha` tag resolved to
index `sha256:dd279f9eaffaf5e2af22173b60ac6437b70d04fca8d867873833102d5af53ae6`.
The measured platform is **linux/amd64**, with manifest
`sha256:62764744c42302386ed746a93c8ca15ee7464b75a436a8cc6acb2e9be675a9e3` and
config `sha256:84fce4473f73cf77a81974314ba4382043fec2d49cce955cdffdbe4b84b2a683`.
Its environment records `VERSION=11.0.0-alpha.3`. The
[source tag](https://github.com/Fiestaboard/FiestaBoard/tree/v11.0.0-alpha.3)
and successful
[release run](https://github.com/Fiestaboard/FiestaBoard/actions/runs/44009121846)
identify `83236253aa8103db856b7efa456e088b9c9ec548`. The image has no source-revision
label; this is corroboration, not a source attestation.

The client COPY layer (zero-based 18) and all later layers through 30 were
downloaded over the public Registry HTTPS API without executing the image.
Compressed SHA-256/length and uncompressed diff IDs were verified. Only regular
files under `app/web/build/client` were copied. Relevant whiteouts or links would
abort extraction. Layer 30 repeats all 542 client files with identical hashes;
layers 19–29 do not modify that subtree. Raw layers and extracted assets are
retained in the program's `status/prodPerf-evidence` directory. The committed
[sample](../../../scripts/perf/published-v11-alpha3.json) records every path,
size and hash, plus immutable provenance.

| Metric | Observed raw bytes | CI ceiling |
| --- | ---: | ---: |
| All JavaScript, 256 files | 6,421,698 | 7,064,576 |
| All CSS, 2 files | 255,096 | 281,600 |
| Fonts, 5 files | 138,068 | 152,576 |
| Largest JavaScript file | 576,617 | 634,880 |

There is **one unique published artifact sample**, not repeated timing samples.
It includes lazy route and locale chunks and the service worker. These totals
are not the initial payload of any route. The inventory also records 251 source
maps (20,796,328 raw bytes) as image-storage cost; nginx refuses `.map` requests,
so maps do not count toward served-code ceilings. Other assets are inventoried
but not currently budgeted.

Per-file gzip level 6 estimates total 2,030,119 JavaScript bytes and 41,051 CSS
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

## Runtime gates still open

No API p95 baseline, LCP, INP, or memory-soak result is established by this PR.
Local process inspection was sandbox-denied; the owner requires verifiable PROD
exclusion before any Docker use. No local Docker command or application suite
ran. Artifact measurements used macOS 27.2 arm64 and Python 3.9.6; host CPU model
and RAM queries were also denied. A contemporaneous load observation was
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
