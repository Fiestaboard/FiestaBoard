# Native iOS API access

This is the implementation record for one ongoing draft pull request against
FiestaBoard 10.1.2. The first milestone is safe optimistic page editing through
the existing shared page API. Collections, schedules, and the remaining native
parity work are followups. The page contract below enables bounded native page
saving when the client explicitly opts in and verifies its support conditions.

## Accepted page contract

`GET /v1/pages`, `GET /v1/pages/{id}`, page creation, and successful page updates
expose a nonempty opaque `revision` and exactly
`"edit_protocol": "page-revision-v1"` on each stored page. Successful updates
return `{"page": <stored page>, "incompatible_references": [...]}`. The legacy
`/pages` routes expose the same model and use the same service and storage.

`page-revision-v1` identifies this page editing feature contract independently
of mutable package/build versions. Its bounded native use is a sparse update
of changed `name` and/or fixed-slot `template` fields, with the original
`expected_revision`. Omit unchanged fields and retain template slot order,
empty strings, Unicode, markup, geometry, line metadata, and other content.
This protocol does not add rich, canvas, collection, or geometry editing to a
native adapter. Other existing `PageUpdate` fields remain available to existing
clients; this advertisement does not narrow the server's legacy API.

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
- `edit_protocol` is computed response metadata. Supplied values in create,
  update, or stored page input are ignored and cannot change the advertisement.
- Page PUT stores the page and invalidates its preview cache. It does not
  directly send to hardware, select the active page, or acknowledge board
  delivery. A running display may later render saved content through its
  normal display cycle. Board controls retain separate authorization and
  compatibility checks.

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
and every update. Both `revision` and `edit_protocol` are runtime metadata and
are excluded from `pages.json`; the persisted schema remains version 6.
Revisions are not timestamps or content hashes. Identical-content ABA and
deletion followed by recreation of the same
ID cannot revive an old generation.

Restarting or reloading the store deliberately invalidates **all** previous
tokens, including drafts whose contents happen to be unchanged. The client
must reload and reconcile. This favors conservative conflict handling over
accepting edits based on an earlier process generation.

The service uses the storage's existing reentrant lock around precondition
checks, geometry/canvas retarget preparation, validation, and mutation. Direct
storage mutations use that same lock. Deletion takes the established outer
lock order (`settings`, `config`, `pages`, `collections`, `schedules`) before
checking its precondition and references and updating dependent selections.
This matches panel content resizing and avoids a page/config lock inversion.
Update/retarget preparation and default/replacement page construction use
model-only geometry validation and storage operations; they do not acquire
outer settings/config locks from inside a page-only critical section.
Backup restore writes and reloads the
same live page storage while holding its owning lock, before releasing it;
cached service references therefore see the restored generation too. The page
singleton is retained rather than replaced later during service reload.
If a restored page document cannot be loaded (for example, a future schema),
the restore raises and its pre-restore pages are removed from the live cache;
cached requests cannot keep reading or saving that obsolete document. Restore
remains nontransactional across files, as documented by the backup service.
A subsequent successful explicit load of a supported document clears the JSON
store's future-schema refusal. Failed loads, absent-file loads, and attempted
writes while the future document remains in place keep the refusal latched.

These guarantees rely on FiestaBoard's existing single Python process and one
live page service per data directory. `supervisord.conf` starts one uvicorn
without `--workers`, and `get_page_service()` caches that owner. This does not
add a distributed lock or support independently constructed concurrent stores,
multiple API workers, or out-of-process edits to `pages.json`. Use the supported
backup restore flow rather than editing the live file.

## Native compatibility and remaining gaps

A native page adapter must require the exact known `page-revision-v1` protocol,
a nonempty original revision attached to its loaded draft, and explicit
session opt-in before issuing page PUT. Missing/unknown protocols and old
servers remain read-only. A revision alone is insufficient. The protocol is
feature discovery, not authentication or universal native write permission;
the normal authentication middleware still applies. Page support must not
broaden access to board controls, which retain their separate exact-version
gate.

The existing API returns typed Pydantic `Page` data, not an arbitrary lossless
raw JSON document. `Page`, `PageUpdate`, and nested models currently ignore
unknown fields; models also normalize geometry. A client cannot safely promise
an unknown-field-preserving whole-document round trip through these routes.
This milestone retains partial updates for supported fields and does not
silently establish a new raw-document endpoint. Unknown nested canvas/row
extensions and future page fields require a separately audited contract before
native editing of those fields can be enabled. A native client can preserve
unknown fields in its local raw document while sending only changed supported
fields, but cannot infer that the backend preserves arbitrary unknown data on
disk. Parsed known models are distinct from invalid raw entries that storage
already preserves to avoid deleting unparseable pages.

The synthetic boundary fixture
`tests/fixtures/page-editing/page-revision-v1.json` provides complete read/save
shapes, a sparse request, and a 412 body for native tests. Its revisions and
timestamps are illustrative, never recorded hardware data. The HTTP test
checks both route families against it, substituting only runtime revisions and
the save timestamp. The panel is a supported 3×15 grid. Native legacy fixtures
with no revision/protocol remain read-only; a permissive native 2×4 read fixture
is below the backend's current minimum grid dimensions and must not be used as
proof of a server-valid save request.

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
  failures were not reproduced; that initial run was not a clean full-web-suite
  result.

### Review corrections

Independent review identified and reproduced a cross-store delete/resize
deadlock and a future-schema refusal that survived a later compatible restore.
New tests first failed against the reviewed implementation: the controlled
resize/delete schedule produced bounded lock-acquisition timeouts, and the
recovery sequence raised `SchemaTooNewError` even after restoring schema 6.
The lock-order and successful-reload corrections preserve the same live owner
and keep the revision check atomic with deletion. The recovery test checks
future-file write refusal before compatible restore, then successful
conditional service update and deletion afterward.
The revised focused Python run passed 523 tests, including all 15 revision
tests, the JSON storage kernel, and panel content resizing. Changed-file Ruff
and `git diff --check` passed. No complete Python rerun was attempted after the
OOM event.

### Final corrected web validation

After mounting the shared fixture and limiting concurrency to two workers, the
complete web suite passed: **259 files, 3,060 tests passed, seven skipped** in
184.51 seconds. This replaces the unresolved full-web result above; the initial
failure history and the incomplete Python full-suite/OOM result remain recorded.
The test run used the exact-lockfile dependency image with no network access.
Run from the repository root:

```sh
docker run --rm --name fiestaboard-ios-api-web-corrected --network none \
  --mount "type=bind,src=$PWD,dst=/source,readonly" \
  --entrypoint sh fiestaboard-ios-api-node:10.1.2 \
  -c 'cp -R /source/web/. /web/ && ln -s /source/tests /tests && npm run test:run -- --maxWorkers=2'
```

### Page protocol advertisement validation

The bounded `page-revision-v1` addition passed 435 focused Python tests and
87 additional response/schema/HTTP contract tests, including all 22 revision
tests. Five new advertisement cases first failed with missing `edit_protocol`;
the sparse-save/hardware-access regression cases already passed against the
existing behavior. A disposable mutation that removed only the persistence
exclusion failed the new disk-absence assertion. No mutation touched the host
checkout. The page response-shape golden was repinned with only the intended
`revision` and `edit_protocol` keys; its previous fixture predated both fields.
Changed-file Ruff checks, formatting, and `git diff --check` passed. Existing
FastAPI/datetime deprecation warnings remain. This wave ran no full Python or
web suite and makes no hardware-delivery claim. Containers used the existing
`fiestaboard-ios-contract:clean` image, read-only source/root filesystems,
writable tmpfs, no hardware mounts, and `--network none`.
