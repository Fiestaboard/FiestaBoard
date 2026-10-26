# Native iOS API access

This is the implementation record for one ongoing draft pull request against
FiestaBoard 10.1.2. The first milestone is safe optimistic page editing through
the existing shared page API. Collections, schedules, and the remaining native
parity work are followups; this milestone does not enable native remote saving.

## Accepted page contract

`GET /v1/pages`, `GET /v1/pages/{id}`, page creation, and successful page updates
expose a nonempty opaque `revision` on each stored page. The legacy `/pages`
routes expose the same model and use the same service and storage.

- Update: `PUT /v1/pages/{id}` with the usual partial `PageUpdate` body plus
  `"expected_revision": "<revision read for this page>"`.
- Delete: `DELETE /v1/pages/{id}?expected_revision=<URL-encoded revision>`.
- A mismatch returns HTTP 412 with the standard `{"detail": "..."}` error
  explaining that the page changed and must be reloaded. The failed operation
  does not change the page, its references, or its revision.
- Missing IDs return 404. Tokens are bound to the page ID by the storage lookup;
  a token read from another page cannot authorize a mutation.
- Preconditions are optional for compatibility. Existing unconditional writers
  still succeed, and every successful storage update generates a new token,
  even if the content is identical. They invalidate previously read tokens.

Clients must retain their draft's original revision, send it when saving or
deleting, and retain unsaved content after 412. They must fetch the changed page
and explicitly reconcile before retrying. Automatically fetching a fresh token
and resubmitting an old draft defeats the protection.

The web page editor carries its seeded revision through button saves,
imperative saves, and deletes. A dirty draft keeps that token during background
refetches; successful imperative saves advance it. Other AI/internal/legacy
writers remain unconditional. Consequently this milestone protects editors
that supply preconditions and does not claim every first-party writer uses CAS.

## Generation and atomicity

Revisions are random UUID generations assigned by `PageStorage` on load, create,
and every update. They are runtime metadata and are excluded from `pages.json`;
the persisted schema remains version 6. They are not timestamps or content
hashes. Identical-content ABA and deletion followed by recreation of the same
ID cannot revive an old generation.

Restarting or reloading the store deliberately invalidates **all** previous
tokens, including drafts whose contents happen to be unchanged. The client
must reload and reconcile. This favors conservative conflict handling over
accepting edits based on an earlier process generation.

The service uses the storage's existing reentrant lock around precondition
checks, geometry/canvas retarget preparation, validation, and mutation. Direct
storage mutations use that same lock. Backup restore writes and reloads the
same live page storage while holding its owning lock, before releasing it;
cached service references therefore see the restored generation too. The page
singleton is retained rather than replaced later during service reload.
If a restored page document cannot be loaded (for example, a future schema),
the restore raises and its pre-restore pages are removed from the live cache;
cached requests cannot keep reading or saving that obsolete document. Restore
remains nontransactional across files, as documented by the backup service.

These guarantees rely on FiestaBoard's existing single Python process and one
live page service per data directory. `supervisord.conf` starts one uvicorn
without `--workers`, and `get_page_service()` caches that owner. This does not
add a distributed lock or support independently constructed concurrent stores,
multiple API workers, or out-of-process edits to `pages.json`. Use the supported
backup restore flow rather than editing the live file.

## Native compatibility and remaining gaps

A nonempty revision on a read is a discovery hint for the conditional page
contract. It is not blanket permission for a native client to write to an
unknown FiestaBoard release. Native remote save remains disabled until an
audited release adapter verifies the rest of the page contract.

The existing API returns typed Pydantic `Page` data, not an arbitrary lossless
raw JSON document. `Page`, `PageUpdate`, and nested models currently ignore
unknown fields; models also normalize geometry. A client cannot safely promise
an unknown-field-preserving whole-document round trip through these routes.
This milestone retains partial updates for supported fields and does not
silently establish a new raw-document endpoint. Unknown nested canvas/row
extensions and future page fields require a separately audited contract before
native save can be enabled. Parsed known models are distinct from invalid raw
entries that storage already preserves to avoid deleting unparseable pages.

Remaining work in this ongoing PR, where required by native parity:

- Define and verify lossless document compatibility and explicit support gates.
- Extend conflict protection to collections and schedules and audit their writers.
- Migrate additional AI/internal writers to preconditions where their edit flow
  can retain an original read generation.
- Complete native adapters for existing internal API surfaces, authentication,
  OAuth handoff, CSRF, validation, and server-version handling. The web UI is a
  static SPA using the existing `/api` surfaces; this work does not require a
  separate mobile API namespace or a new metadata endpoint.

## Validation plan

Tests use temporary files and FastAPI's in-process client in disposable Docker
containers with no hardware mounts and no test network access. Python imports
and dependencies stay inside Docker. Web dependencies are installed from the
checked-in lockfile in a disposable image; tests run with networking disabled.

Regression coverage includes native/web save order in both directions, true
concurrent conditional writes, legacy writer invalidation, identical-content
ABA, delete/recreate, restart, restoring the same document through a cached live
service, HTTP behavior on both route families, and web revision carriage after
background refetch and repeated imperative saves. New regression tests were
observed failing before their covered production behavior was implemented.

### Validation results for the first milestone

- 241 focused Python tests passed: page revisions, pages, retargeting, backup,
  restore rollback, page contracts, and router decoupling.
- 198 additional Python tests passed: API conventions, v1 contracts/board
  restore, operation registry, wiring, and teaching. The 13 new revision tests
  were also rerun separately against the committed patch and passed.
- The complete Python suite was attempted but did not finish: Docker emitted
  an OOM event and exit 137 after 232 seconds, with pytest progress at 54%.
  There is no full-suite pass claim.
- 98 targeted web tests passed using dependencies installed from the exact
  checked-in lockfile. TypeScript typecheck, changed-file Ruff and Prettier
  checks, and `git diff --check` passed.
- The full web run reported 3,051 passing tests, three failing tests, seven
  skipped tests, and one additional suite setup error. The setup error was a
  missing shared geometry fixture in the disposable test harness. The failing
  tests were `activate` manual consent-heading focus, `page-builder-canvases`
  preview issues, and `setup-wizard-choose-output` failed Vestaboard test flow.
  With the fixture correctly mounted, all four affected files passed in
  isolation (59 tests) both on the pristine base and on this patch. The initial
  failures were not reproduced; this is not a clean full-web-suite result.
