# Production accessibility route survey

This is a bounded **automated survey**, not a WCAG conformance certification or a full flow audit. It surveys nine configured routes and two browser-synthesized Panel error states at 1280×800, 900×984 and 390×844 in light/dark. The 390 project has touch/mobile input; the other projects use desktop input. Normal motion remains enabled. Manual keyboard/focus/dialog/error announcements, screen readers, zoom/reflow, target exceptions and every additional route state remain separate work.

The `.audit.ts` suffix deliberately excludes this spec from ordinary Playwright discovery. Use its dedicated config. It imports neither the ordinary config nor `tests/helpers.ts`; there is no global setup, data deletion, board configuration or server startup. The browser blocks and reports every request except GET/HEAD/OPTIONS. Panel mocks are explicitly labeled and cannot be reported as backend observations. The service worker is blocked so a cached bundle cannot silently replace the campaign target; offline/PWA behavior needs its own campaign.

## Before execution

The operator must establish PROD exclusion using the authorized process inventory and reserve the shared hub within the total three-container cap. Use only dedicated synthetic data, including any saved login session. Record the running container's immutable image digest/source provenance separately; environment variables here are declarations, not image attestation. Provision a configured hub before this survey. It will fail first-run/auth/API/route preconditions instead of skipping them or scanning a loader.

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

From the worktree's `web/` **inside the approved container**, run exactly one spec with one worker:

```sh
npx playwright test --config tests/prod-a11y/playwright.config.ts routes.audit.ts --workers=1
```

Use `--project=desktop-light` or `--grep` for a bounded first run; preserve the other projects as unrun until executed. No command above provisions a container or authorizes concurrent PROD use.

Each test saves campaign/auth preflight, full axe JSON, all rule options, browser/axe versions, actual viewport/theme/input details, screenshot and any blocked write requests. Axe enables WCAG 2.0 A/AA, 2.1 A/AA and 2.2 AA, including explicit `target-size` and contrast. **All violation impacts fail.** Incomplete results are retained and annotated as needing manual review even when the automated test passes. Readiness failures retain failure-state artifacts and do not become axe passes. No retries are configured.

The result covers only the currently seeded state. An empty list is not a populated-list pass, a synthetic Panel 404 is not a real backend failure test, and a screenshot/axe pass does not establish keyboard or spoken output. Pair results with the criterion/state ledger in `program/reviews/PROD-prodA11y.md` and keep all unrun states visible.
