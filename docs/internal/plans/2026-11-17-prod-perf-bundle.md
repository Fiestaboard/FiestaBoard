# Published v11 bundle regression plan

> For agentic workers: use the executing-plans and test-driven-development skills. Keep the independent source audits and final review in separate checkouts.

**Goal:** Add a deterministic bundle regression gate grounded in the published v11 alpha.3 artifact while preserving the remaining production performance gates as unrun.

**Architecture:** A standard-library offline utility inventories a copied `web/build/client` directory, records hashes and raw/gzip sizes, and checks explicit raw-byte limits. The existing E2E job measures its already built image after the browser tests; no additional image build or runtime is needed. Existing checks and release workflows remain unchanged in meaning.

**Spec:** The prodPerf handoff requires published-image API p95, bundle, desktop/phone LCP/INP, and two-hour accelerated soak evidence. This plan covers only the artifact-size part. Process inspection is denied locally, so the explicit PROD serialization rule prohibits Docker. Runtime measurements and their budgets remain deferred, not passed. Program reports retain the source-backed runtime continuation plan.

**Tech stack:** Python standard library (3.9+), existing GitHub Actions E2E job, public OCI metadata and verified filesystem layers.

## Constraints and decision

- Only the task worktree; no primary checkout, product UI, API, release or publishing edits.
- No Docker commands locally until `ps` verifies PROD exclusion. No host application server or dependency installation.
- Utility scripts below are explicitly supported for local execution: they inspect files and use only the standard library.
- Jev chose the offline bundle gate with probability 1.0 over evidence-only and an unvalidated full runtime harness. This is advice, not proof of a performance pass.
- Published artifact source is `83236253aa8103db856b7efa456e088b9c9ec548`; task base is `4490b28d852a5ccf77ee1de3c55c534f586eab51`. Never conflate the two.
- One measured artifact gives deterministic size evidence, not a latency distribution. Baseline-relative headroom is a size-regression policy, not a user-experience target.

## Review focus

- Empty/missing build directories must fail, not produce a zero-size pass.
- Missing/invalid budget keys must fail closed.
- Source maps must remain visible as storage cost but excluded from served-code budgets because nginx refuses them.
- Symlinks must not let a directory scan escape or silently skip files.
- A strict one-byte overshoot must fail and retain a machine-readable report; equality passes.

## Task 1: Published artifact evidence

- [x] Pin current public tag, index, amd64 manifest and config; verify digests.
- [x] Download the client-copy layer and all later layers; verify compressed hashes and uncompressed diff IDs. Replay only regular client files; reject relevant whiteouts/symlinks rather than guessing.
- [x] Retain raw layers, assets, per-file hashes and provenance under the program evidence directory. Record hardware limits and load observations without inventing inaccessible fields.

## Task 2: Offline inventory and budgets

Files: `scripts/perf/bundle_budget.py`, `scripts/perf/test_bundle_budget.py`, `scripts/perf/bundle-budget.json`, `scripts/perf/published-v11-alpha3.json`.

Interfaces: `measure(client: Path) -> dict` produces sorted per-file sizes/hashes, aggregate raw bytes for JavaScript, CSS, fonts and largest JavaScript, plus gzip estimates and source-map storage. `check_budget(report: dict, budget: dict) -> list[str]` validates required numeric limits and returns violations. CLI writes `--report` before returning nonzero for exceeded limits.

- [x] Write failing tests for exact byte totals, excluded maps, missing JS/CSS/index, symlinks, invalid budgets, equality and overshoot, and CLI failure evidence.
- [x] Run the standalone utility tests and observe the missing behavior.
- [x] Implement the smallest utility meeting those contracts; rerun all utility tests.
- [x] Measure the real extracted artifact. Set explicit raw-byte ceilings at 10% above each observed category and largest JS, rounded up to 1 KiB. Document this as reviewable growth allowance, not statistical calibration. Gzip stays informational to avoid compressor drift in the gate.
- [x] Compare utility inventory independently with filesystem sizes and hashes; preserve the actual sample and commands.

## Task 3: CI and review

Files: `.github/workflows/ci.yml` (additive E2E steps only), `docs/internal/development/PERFORMANCE.md`, `.changeset/published-bundle-budget.md`.

- [x] Add standalone utility tests, copy the built image's client directory after existing E2E tests, apply budgets, upload report even on budget failure. Add no runtime containers or rebuilds.
- [x] Document reproduction, observed sample counts, scope, rationale, and open runtime gates.
- [x] Run utility regression tests and whitespace checks. Record full application suites/build/browser checks as locally blocked; observe hosted checks separately.
- [ ] Commit with the required Claude trailer, request independent Astra review at the exact head in its separate checkout, and address demonstrated findings.
- [ ] Push normally and open a v11 PR with the required footer. Observe CI at the exact head. Update prodPerf status/review and ownership; do not mark overall prodPerf READY without runtime evidence.

## Continuation verification ledger

2026-11-17: inherited WIP retained. Fresh standalone suite: 12/12 pass; Ruff lint and format pass after one SIM117 and two formatting repairs. Three independent temporary-copy mutants (allow one-byte overshoot, ignore service worker, count source maps as served JS) each fail the tests; original files retained. Published artifact remeasurement matches all four raw metrics. Original RED log is a missing-module failure; mutation evidence supplies behavioral checks. Independent artifact audit confirms all 13 layer hashes/diff IDs and 542 files. Local application suites/build/browser/axe are UNRUN because PROD exclusion is unavailable; no Docker used.

Ruling: retain the already-recorded Jev offline_bundle_gate decision (p=1.0); no new unchanged-question call. Dispatcher RUNNING also lists prodA11y, while ps remains denied. Complete this offline step and leave runtime work for serialized resumption. No product UI files changed, so this PR has no new drawn state or Figma parity claim.

Review fix: Astra r1 reproduced a silently skipped unreadable subtree. Real chmod-000 regression failed first (PermissionError not raised); strict iterdir traversal now propagates read errors, and the full utility suite passes 13/13 with no skip. Lint/format pass and baseline remeasurement unchanged. Raw RED/GREEN logs retained in program evidence.
