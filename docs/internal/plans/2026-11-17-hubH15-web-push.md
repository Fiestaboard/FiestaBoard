# H15 Web Push Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task. Parent coordinates independent final code/API and security review.

**Goal:** Supply the secure backend web push contract needed by web 2.13.

**Architecture:** A private SQLite database owns generated P-256 VAPID material, account-generation consent and browser-session subscriptions. Browser-only routes reuse the existing session, Origin and CSRF gates. A synchronous notifier uses `pywebpush` cryptography with an HTTPS transport that allowlists browser providers, validates DNS results and pins the connection while preserving TLS hostname checks.

**Tech Stack:** Python, FastAPI/Pydantic, SQLite, `pywebpush`/cryptography, standard-library HTTPS.

**Spec:** `/Volumes/ExtHD/fiestaboard-universal-design/program/status/hubH15.md`, MASTER-PLAN Phase 3 H15 and shared WEB-SLICE-BRIEF.

## Global Constraints

- Target `v11`; minor changeset; exact `Co-Authored-By: Claude <noreply@anthropic.com>` trailer.
- All runtime verification in the coordinator's shared `fb-dev-py`; no host installs or tests.
- No UI, merge, force push, GitHub comments, or changes to primary working trees.
- No private keys, subscription endpoints or browser encryption keys in API output, backups, or logs.
- Opt-in must hold for both the user and the current browser device; revoked or expired sessions cannot receive notifications.

## Review Focus

- Cross-account/device mutations and native token privilege widening: route denial and independently scoped preference tests.
- DNS rebinding, local addresses, redirects, proxy settings: pinned socket and transport boundary tests.
- In-flight renewal racing 404/410: revision compare-delete tests.
- Corrupt/missing stores and concurrent VAPID generation: fail-closed and cross-instance tests.
- Expiry, bounded retries and consent revoked between attempts: deterministic notifier tests.

## Decisions

Jev selected `private_sqlite_allowlist_pinned`, probability 0.90 (confidence 0.88), over unrestricted public HTTPS and private JSON. Verify guarantees with tests; probability is advisory. Supported providers initially FCM, Mozilla push service and Apple web push. A device is a browser session: signing out ends push delivery and signing in again requires subscription registration. Account consent is tied to the existing account generation. No event category policy or frontend is introduced.

### Task 1: Persistence and browser contract

**Files:** Create `src/push/{__init__,models,store,routes}.py`, `tests/test_web_push.py`; modify `src/api_server.py`, `requirements.txt`, `pyproject.toml`.

**Interfaces:** `PushStore(path)`, `get_push_store()`; `GET /push/status`, `PUT /push/preferences`, `PUT /push/subscription`, `DELETE /push/subscription`. Status exposes public VAPID key, user/device opt-in and expiry only. Request subscription has standard `endpoint`, `expirationTime`, `keys` fields.

- [ ] Add contract tests: absent feature yields 404; defaults false; independent device opt-in; CSRF/Origin/token denial; invalid keys/URLs; persisted private key and permissions; concurrent registration and key initialization; export exclusion.
- [ ] Run shared-container focused tests and record observed RED.
- [ ] Implement private transactional storage and strict input/output projections; unique endpoint ownership, bounded subscription count, revision tokens.
- [ ] Run focused tests; commit with required trailer.

### Task 2: Transport and notifier

**Files:** Create `src/push/{transport,notifier}.py`, `tests/test_web_push_delivery.py`.

**Interfaces:** `PushNotifier(store, auth).notify(username, payload, ttl_seconds=300)` returns sent/failed/skipped/expired counts. No arbitrary network-send HTTP endpoint.

- [ ] Add transport tests for provider URL validation, mixed/private DNS, original TLS hostname with pinned public address, no redirects/proxies, response body not read/logged. Add delivery tests for encryption/VAPID, 404/410 deletion, retryable network/429/5xx statuses, bounded three attempts/backoff, payload/TTL bounds, expiry, consent/session recheck and stale-revision deletion.
- [ ] Run tests to observe RED.
- [ ] Implement `pywebpush` adapter and synchronous bounded notifier; transport times out, errors carry no endpoint/body; check consent before each attempt.
- [ ] Run focused tests; commit with required trailer.

### Task 3: Documentation and verification

**Files:** Create `docs/development/web-push.md`, `.changeset/hub-h15-web-push.md`; update generated API reference if schema generator changes it and README feature link.

- [ ] Document exact browser API, account/session lifetime, supported providers, secure-context prerequisite, VAPID subject setting, internal notifier invocation and limits, storage/export exclusion.
- [ ] Verify internal OpenAPI declares browser-only authentication and strict shapes; generate reference from actual app schema.
- [ ] Run complete pytest and ruff in shared container, retain logs on ExtHD; address failures without weakening checks.
- [ ] Commit documentation; report exact SHA/tests and remaining limitations to parent for independent review. Parent owns push/PR/CI.

## Consumer contract refinement

Reviewer inspected actual frame `59:13890`: four category switches and Send a test.
Jev chose `sender_test_capabilities` with p=1.00: add rate-limited, CSRF-protected
`POST /push/test` with server-owned text, current device only, and no arbitrary
payload or endpoint; status returns `event_sources: []` and `test_available`.
Four producer integrations (display offline, override ended, hub/plugin update,
silence-held message) remain an explicit web 2.13 dependency, rather than falsely
advertising that generic delivery has wired those events. Add typed service
orchestration and opt new domain into conventions/layering ratchets.
