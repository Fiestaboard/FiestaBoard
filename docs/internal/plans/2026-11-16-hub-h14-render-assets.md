# H14 renderer assets implementation plan

> Execute test-first; use a separate astra reviewer on the exact final head.

**Goal:** Let native iOS and Android clients retrieve the hub's built-in LED fonts and character sets as one versioned, revalidatable snapshot.

**Architecture:** `GET /v1/render-assets` serves the existing vendored maps through a typed envelope. Preserve the nested FiestaUI camelCase documents and optional-field omission. `schema_version: 1` versions the wire format; `revision` hashes the canonical fonts/character_sets content. The quoted SHA-256 ETag hashes the actual serialized response bytes. `Cache-Control: private, no-cache` permits storage but requires authenticated revalidation. Conditional GET supports exact, weak, comma-list, wildcard and repeated If-None-Match values. A match returns an empty 304 with the same cache headers. No charset materializer or bitmap copy is introduced.

**Spec:** program MASTER-PLAN Phase 3 H14 and owner handoff. Built-ins only, not dynamic plugin sets; no native app changes, TV scope expansion or web UI changes. Normal mobile control credentials already reach `/v1/*`. No Figma visual surface changes.

**Decision:** Jev chose combined catalog (p=0.97, confidence=0.96) over separate font and charset resources to keep a small atomic cache snapshot. Use existing vendored source metadata (`source`, `commit`, `version`) in a `source` field. Content revisions are distinct from upstream versions and per-charset versions.

## Constraints

- Target `v11`; no merges, approvals, VRT approvals or GitHub comments.
- Work exclusively in `fb-wt/cx-hubH14`; exactly the Claude coauthor trailer and required PR footer.
- Shared Docker pool only; no per-task images or persistent containers. No host test execution or dependency installation.
- Full pytest and ruff; generated API reference and route inventory; native response fixtures; minor changeset.

## Review focus

- Revalidation must still authenticate, including revoked/invalid credentials.
- Preserve charset Unicode, aliases and omitted optional fields.
- ETag and revision change when bitmap or charset content changes.
- Conditional GET handles weak/list/repeated headers without false matches.
- Native fixture bytes and schema must represent real responses, including empty 304.

## Task 1: versioned resource and native contract

Files: new `src/v1/render_assets.py`, `src/v1/routes_render_assets.py`, `tests/test_render_assets_contract.py`; additive `src/v1/__init__.py`, `tests/test_v1_contract.py`; generated `tests/golden/api_routes.json`, `docs/reference/api-endpoints.md`; new native documentation, fixtures/recorder and `.changeset/h14-render-assets.md`.

- [ ] Write endpoint tests asserting 200 envelope and exact original maps, stable revision/ETag, 304/header behavior, source metadata, strict schema and auth boundaries.
- [ ] Run tests in Docker and observe intended 404 failures before adding production code.
- [ ] Add typed source/font/charset/envelope models and deterministic serialization; mount GET handler with header/error/OpenAPI declarations.
- [ ] Run focused endpoint, v1, auth, conventions, vendored-data tests and prove content mutations alter validators.
- [ ] Record real TestClient API responses and verify native fixture body/hash/header provenance; generate route inventory and OpenAPI reference.
- [ ] Run full pytest, ruff check/format and documentation checks; fix observed failures with test evidence.
- [ ] Commit, push normally, create PR into v11, have separate astra reviewer assess exact head; address up to three rounds, await green CI.
- [ ] Update program status and WORKTREES row with actual results and outstanding limits. Never claim native apps have switched from bundled assets.
