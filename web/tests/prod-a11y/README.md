# Production accessibility route survey

This is a bounded **automated survey**, not a WCAG conformance certification or a full flow audit. It covers empty Pages, empty Collections, the Monitor tombstone and two browser-synthesized Panel error states at 1280×800, 900×984 and 390×844 in light/dark: 30 source-defined cases. The 390 project has touch/mobile input; the other projects use desktop input. Normal motion remains enabled. Manual keyboard/focus/dialog/error announcements, screen readers, zoom/reflow, target exceptions and every additional route state remain separate work. No case is considered executed merely because it appears in this inventory.

The `.audit.ts` suffix deliberately excludes this spec from ordinary Playwright discovery. Use the dedicated launcher below. It imports neither the ordinary config nor `tests/helpers.ts`; there is no global setup, data deletion, board configuration or server startup. Browser HTTP requests are forwarded to the exact campaign origin without following redirects; external HTTP origins, redirects and methods other than GET/HEAD/OPTIONS are blocked and reported. This is not an OS network sandbox and does not constrain backend egress. Panel mocks are explicitly labeled and cannot be reported as backend observations. The service worker is blocked so a cached bundle cannot silently replace the campaign target; offline/PWA behavior needs its own campaign.

The three application states require complete Pages and Collections stores with `pages: []` / `collections: []` and `total: 0`; a filter producing an empty view is insufficient. The shell fixture requires one synthetic board, AI disabled, data plugins disabled and no settings-restore notice. Output/transition plugins do not contribute to the navigation attention badge; their observed flags are recorded without requiring a nonexistent enable toggle. Visible empty titles or the Monitor's `Monitoring Removed` / `docker logs fiestaboard` markers must appear. Required shell APIs must finish successfully, and all observed API requests must settle without unexpected failures. Populated routes are deliberately unsupported: they make read-only preview/validation POSTs, and this runner must not block them and then misreport their broken state as ordinary route coverage.

## Before execution

The operator must establish PROD exclusion using the authorized process inventory and reserve the shared hub within the total three-container cap. Use only dedicated synthetic data, including any saved login session. Record the running container's immutable image digest/source provenance separately; environment variables here are declarations, not image attestation. Provision the configured empty/static fixture above before this survey. It will fail first-run/auth/API/route/fixture preconditions instead of skipping them or scanning a loader. API preflights explicitly refuse redirects. The launcher reserves a fresh run directory; reuse of a run ID must fail rather than overwrite previous evidence.

### Prepare the synthetic dataset

After the resource gate, run `scripts/prod_a11y_seed.py` from the repository root inside the approved Python container. Supply an existing canonical absolute parent on the mounted ExtHD evidence path and a fresh dataset ID:

```sh
python scripts/prod_a11y_seed.py \
  --parent /evidence/datasets \
  --dataset-id prod-a11y-alpha3-empty-unique \
  --acknowledge-synthetic-only
```

`/evidence/datasets` represents an approved mounted evidence directory; the tool does not create the parent, mount anything or start a container. It refuses an existing destination, including empty directories and symlinks. A partial failure remains reserved; use a new ID rather than deleting or reusing it.

Mount only the resulting `data/` directory at the leased hub's `/app/data`. Keep `seed-manifest.json` and `seed-manifest.sha256` outside that mutable mount. Verify their digest and every listed input hash before boot; both manifest files must exist before treating the seed as complete. Boot can mutate the input files, so preserve the initial manifest and record the subsequent observed state separately. Use the dataset ID as `AUDIT_DATASET_ID`.

The fixture contains one synthetic FiestaPanel output with no physical board connection, empty Pages/Collections/Schedules/Panels stores, completed setup, disabled sign-in/AI/data integrations/MQTT, disabled plugin auto-update and manual system updates. It was designed against alpha.3 source; successful loader tests against a newer checkout would not establish alpha.3 image behavior. Use a clean container environment without inherited credentials or configuration overrides. The production entrypoint creates its own updater token and may probe a sidecar; the shell also queries public update metadata. This fixture does not establish backend network isolation. The running-image provenance and browser preconditions still must be observed.

### Check evidence protection

Run these focused checks sequentially inside the approved containers, with the complete task checkout mounted:

The Python suite also requires the repository's locked first-party output seed through `FIESTABOARD_OUTPUT_SEED_DIR` or the image's `/opt/fiestaboard/seed/outputs`. Use a seed built from this checkout's `outputs.lock.json`; `tests/conftest.py` validates it before collection and does not fetch missing outputs. Provisioning that test dependency is separate from creating the synthetic hub dataset.

```sh
# Repository root, approved Python container
python -m pytest tests/test_prod_a11y_seed.py -n 2 -q --no-cov

# web/, approved Node container
node --test tests/prod-a11y/run.test.mjs
```

The launcher checks use the actual launcher with a deliberately destructive fake CLI; they exercise reservation, duplicate-ID preservation, fixed execution controls and failure receipts without a browser or hub. They do not validate real Playwright configuration loading. After installing locked web dependencies, use a fresh run ID and the full campaign environment below for `node tests/prod-a11y/run.mjs --list`; this is a case inventory, not a browser pass. Repeat that run ID and verify refusal before child startup and unchanged evidence hashes. Also verify that direct Playwright invocation without `AUDIT_RUN_TOKEN` is refused by the dedicated configuration before trusting its protection. Retain the commands, exit statuses and before/after hashes. Full typecheck/lint/format/build/coverage and the actual browser/manual audit remain separate required checks.

### Declare the campaign

Set these variables in the approved browser container:

| Variable | Required value |
| --- | --- |
| `BASE_URL` | Dedicated local hub origin, e.g. `http://fb-dev-hub:3000` or the CI localhost origin |
| `AUDIT_SYNTHETIC_ONLY` | `yes`; operator confirms the isolated hub contains no user data |
| `AUDIT_CAMPAIGN` | `published` or `candidate`; run them separately |
| `AUDIT_IMAGE` | Actual immutable image reference, `repository@sha256:<64 hex>` |
| `AUDIT_SOURCE_SHA` | Full 40-character source SHA corroborated by the image provenance |
| `AUDIT_AUTH` | `disabled` or `authenticated` |
| `AUDIT_STORAGE_STATE` | Only for authenticated mode: path to a synthetic session state; never commit it |
| `AUDIT_RUN_ID` | Unique lowercase `prod-a11y-...` identifier per execution |
| `AUDIT_DATASET_ID` | Identifier of the synthetic fixture dataset; retain its separate seed manifest |
| `AUDIT_ARTIFACT_DIR` | Absolute mounted output directory on ExtHD (or CI artifact directory) |

From the worktree's `web/` **inside the approved container**, use the launcher, which selects the dedicated spec/config and one worker:

```sh
node tests/prod-a11y/run.mjs
```

Pass `--project=desktop-light` or `--grep=empty-pages` to the launcher for a bounded first run; preserve the other projects as unrun until executed. Do not bypass the launcher with a direct Playwright invocation. No command above provisions a container or authorizes concurrent PROD use.

Each test saves campaign/auth preflight, full axe JSON, all rule options, browser/axe versions, actual viewport/theme/input details, screenshot, trace and the browser HTTP ledger. Empty/static results record the observed fixture counts, shell data and required API paths. Axe enables WCAG 2.0 A/AA, 2.1 A/AA and 2.2 AA, including explicit `target-size` and contrast. **All violation impacts fail.** Incomplete results are retained and annotated as needing manual review even when the automated test passes. Readiness failures retain failure-state artifacts and do not become axe passes. No retries are configured.

The result covers only these explicit empty/static fixtures. An empty list is not a populated-list pass, a synthetic Panel 404 is not a real backend failure test, and a screenshot/axe pass does not establish keyboard or spoken output. Home, editor, schedule, displays, integrations, settings/account, setup/auth, live Panel/fullscreen, other errors and full flows remain outside this first runner. Pair results with the criterion/state ledger in `program/reviews/PROD-prodA11y.md` and keep all unrun states visible.
