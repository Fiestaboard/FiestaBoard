# Native client API readiness implementation plan

> Continue the approved native-client preparation work using Sol 6.1 implementation agents and Astra review. All backend changes belong to draft PR #2373 on `codex/ios-api-access`.

**Goal:** Complete the identified backend prerequisites in one merge: conditional content editing across pages/collections/schedules and participating tools, document field preservation for richer editors, and verified existing authentication/OAuth access.

**Architecture:** Extend the existing runtime revision/protocol pattern at the owning storage lock. Preserve existing routes and use additive protocol metadata. Maintain a deliberate distinction between compatible unconditional legacy/maintenance operations and participating first-party editors carrying original revisions. Native authentication continues through existing session and OAuth services unless isolated evidence requires an addition.

**Spec:** `docs/development/ios-api-access.md` and the native project's approved full-parity design; this is the expanded backend scope explicitly requested by the user.

## Global constraints

- One branch and draft PR #2373. Use `gh` per user preference. Do not merge or deploy.
- Preserve the original dirty FiestaBoard checkout and native Xcode signing edits. Work in the existing isolated `fiestaboard-ios-api` checkout.
- All backend imports/tests and dependency installation run in disposable Docker containers. Test data only; no production service/hardware/provider calls. Dependencies may be fetched in isolated containers, while fixture tests run without network access.
- Preserve the established cross-store lock order: settings → config → pages → collections → schedules. Conditional check and dependent mutation must be atomic.
- Runtime UUID revisions and edit protocols are excluded from persisted content; load/restart/create/update invalidate earlier generations. Restore and conversion rollback must not resurrect tokens or leave stale cached owners.
- No automatic stale-write retry or fetching a fresh revision immediately before applying an old draft. Keep conflict responses actionable and preserve user work.
- Native-rich unknown-field preservation must be verified across nested structures, not inferred from a top-level round trip. Do not silently change schema migration rules or invent support for unknown behavior.
- Agents have exclusive files, commit only owned changes, and do not launch additional agents. Claude CLI was unavailable because of expired login; no unchanged retry or credential modifications.

## Review focus

1. Both save orders and simultaneous writers must reject stale updates/deletes, including approval-delayed AI actions.
2. Restore/recovery, same-ID replacement, default fallback changes and legacy writers must invalidate affected editors.
3. Cross-store locks must not deadlock with panel conversion, deletion, restore or background workers.
4. Rich nested unknown fields and explicit null/omission must survive unrelated edits without becoming writable runtime metadata or bypassing validation.
5. Native cookie/CSRF/OAuth access must preserve authentication/origin/state boundaries; no new bypass, secret exposure, duplicate callback or broad redirect acceptance.

## Task R — Collection and schedule revision foundation

Owner: content revision agent. Files: `src/collections/**`, `src/schedules/**`, `src/v1/routes_content.py`, `src/backup/service.py`, `src/panels/content_resize.py`, `src/panels/content_resize_recovery.py`, related focused tests/fixtures. This owner also owns the web collection/schedule adapters and editing UI needed to carry original revisions; coordinate shared tests before editing.

- [ ] Add computed `collection-revision-v1` and `schedule-revision-v1` protocols, runtime revisions, optional expected_revision update/delete preconditions and shared 412 behavior on public/legacy surfaces.
- [ ] Include schedule toggles and default-page editing. Document default revision scope, primary fallback invalidation and compatible unconditional writers; carry original revisions through participating web actions.
- [ ] Audit every direct collection/schedule writer, in-place restore and conversion rollback/recovery. Preserve live owners and rotate revisions when replacing data; retain schema refusal recovery.
- [ ] Prove both save orders/concurrency, delete/recreate, reload/restore/recovery, cross-store lock order, null/omission, rejected writes leaving references untouched, and web dirty-draft revision retention. Record red/green evidence.

## Task D — Rich document preservation

Owner: document contract agent. Files: `src/pages/models.py`, `src/pages/storage.py`, page-related nested model definitions (coordinate exact paths first), dedicated new preservation tests/fixtures. Do not edit collection/schedule/backup/ops files owned elsewhere.

- [ ] Inspect top-level and nested page/canvas/row/metadata parse/update/serialize paths and report a bounded preservation design before implementing it.
- [ ] Implement the required contract so supported rich updates preserve unrelated stored fields and future extensions, including nested elements; distinguish replacement from patch semantics explicitly. Keep metadata server-owned and geometry validation intact.
- [ ] Verify unknown future fields, arbitrary numeric/Unicode values, explicit nulls, mixed known/unknown nesting, copy/import/export/restore and schema boundaries where applicable. Existing typed consumers must continue rendering known behavior safely.
- [ ] Provide fixtures and a precise support matrix; do not claim arbitrary unknown behavior is supported just because it is retained.

## Task T — AI/MCP revision carriage

Owner: tool contract agent. Files: `src/ops/**`, `src/mcp_server.py`, applicable `src/ai/**` tool plumbing/prompts and dedicated tool tests. Do not edit storage/routes/web files.

- [ ] Expose revision/protocol on content reads and carry `expected_revision` in edit/delete tools for pages, collections and schedules (including defaults if exposed).
- [ ] Make participating first-party tool edits require the revision of the content originally read. Do not fill it by silently rereading immediately before mutation. Keep explicitly scoped internal maintenance/legacy compatibility where needed and document it.
- [ ] Preserve revision through staging/approval/dispatch and return actionable conflict results without automatic overwrite/retry.
- [ ] Test tool schemas, both native/tool write orders, missing/stale revisions, delayed approval and unchanged unrelated fields. Audit all repository callers of affected executors.

## Task A — Authentication/OAuth and native boundary verification

Root implemented isolated contract verification in `2078e10b5`; no production authentication change was needed. Contract: `native-client-authentication.md`. All 703 selected auth/OAuth tests passed, including 16 new native sequence cases.

- [x] Exercise cookie login/protected reads/logout, session CSRF/origin enforcement and root/prefixed native request shapes using isolated clients.
- [x] Verify authorize/status/manual-complete/disconnect and applicable four OAuth flow state/expiry/denial/replay behavior with mock providers. Establish whether native clients need any backend handoff changes; implement only evidence-backed gaps with regression tests.
- [x] State supported direct/proxy/HA topology boundaries honestly. Do not represent a path-rewrite simulator as real HA authentication.

## Integration and handoff

- [ ] Complete backend/API documentation with exact native payloads, capability discovery, conflict/null/replacement semantics, writer coverage and residual native-only work.
- [ ] Run meaningful focused Python checks and the full web suite. Partition the Python suite into bounded groups if necessary to avoid the previously observed monolithic OOM, recording any unresolved failures accurately.
- [ ] Astra review each substantive track and combined branch; fix actionable findings with original owners and re-review.
- [ ] Refresh the single PR title/body around final scope and verification; resolve base conflicts if present, push, and update native TASKS.md. Leave the PR draft and unmerged for user review.

## Recorded implementation decisions

- Document preservation uses page-scoped tolerant subclasses, keeping the standalone canvas DSL strict. `PageUpdate` remains a sparse known-field update, with supplied lists replacing the complete field. Create/share/import carry opaque extensions while filtering server metadata. `document_protocol: page-document-v1` advertises the bounded value-preserving contract separately from optimistic editing. Jev advised validated extension retention over a parallel raw shadow; source inspection established the narrower page-only scope.
- Default-page revisions conservatively include settings generations so changing the primary board away and back cannot revive an old effective-default token. Schedule-mode controls remain separate settings operations.
- Upstream main version 10.1.3 and preview refresh were merged before final integration.
