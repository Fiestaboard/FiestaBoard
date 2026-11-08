---
description: Shared content editing, revision, and rich document contracts for native clients.
---

# Content APIs for native clients

Draft PR [#2373](https://github.com/Fiestaboard/FiestaBoard/pull/2373) combines
the server preparation for native clients into one merge. Native applications
continue using the same services as the web application. They discover editing
support from returned capabilities, rather than inferring it from a release
number. Authentication is described in
[native-client-authentication.md](native-client-authentication.md).

## Capabilities and requests

Paths below are Python route paths. A normally exposed deployment adds `/api`;
retain any deployment base prefix when constructing URLs.

| Resource | Capability on reads | Conditional write |
| --- | --- | --- |
| Page | `edit_protocol: page-revision-v1`, `revision` | `PUT /v1/pages/{id}` with `expected_revision`; DELETE with query parameter |
| Collection | `edit_protocol: collection-revision-v1`, `revision` | `PUT /v1/collections/{id}` with `expected_revision`; DELETE with query parameter |
| Schedule entry | `edit_protocol: schedule-revision-v1`, `revision` | `PUT /v1/schedules/{id}` with `expected_revision`; DELETE with query parameter |
| Schedule defaults | `edit_protocol: schedule-default-revision-v1`, `revision` from `GET /schedules/default-page?board_id=...` | `PUT /schedules/default-page` with `page_id`, optional `board_id`, and `expected_revision` |
| Rich page content | `document_protocol: page-document-v1` | Supported page fields through the existing create/update/share/import services |

Schedule list responses also include `default_page_revision` and
`default_page_edit_protocol` alongside the effective default. An all-board list
does not identify one editable default; fetch the selected board's state.
Legacy page/collection/schedule routes use the same revision-aware owners as
the public `/v1` routes.

For example, preserve the revision read with the draft and send only intended
page field changes:

```json
{"name":"Kitchen morning","expected_revision":"<original page revision>"}
```

A mismatched revision returns HTTP 412. Keep the draft, fetch the current
resource, and ask the user to reconcile before another save. Never obtain a new
token merely to resubmit an old draft. Missing resources return 404. Revision
tokens are opaque: do not parse, synthesize, or compare their ordering. Bind
them to the selected deployment/resource and discard them when reconnecting to
a different deployment. Unknown/missing capabilities should disable the
corresponding conditional editor.

## Generations and writer coverage

Content revisions are runtime UUID generations. Load/restart, create, and
successful updates invalidate earlier generations; equal-content updates and
delete/recreate cannot revive an old token. Runtime revision/protocol metadata
is excluded from persisted documents and is not editable author content.
Restore reloads content into the live owners rather than leaving cached
requests with obsolete storage. Conversion rollback/recovery invalidates
affected generations too.

Default-page tokens have a deliberately conservative scope: all defaults plus
the settings generation. Changing any default or persisted settings invalidates
them, including changes unrelated to the selected board. This covers primary
board fallback changes and changing a primary board away and back. A client
may therefore encounter a valid conflict even when its displayed default looks
unchanged.

Participating web editors retain the original generation while a draft is
open. Schedule enabled toggles participate as schedule-entry updates. AI/MCP
update/delete/default tools require an original revision and carry it through
approval and dispatch; missing/stale revisions produce actionable errors.
Low-level storage/service and compatible legacy REST writes may omit a
precondition, but still invalidate old generations. This preserves existing
maintenance clients without pretending an unconditional writer cannot
overwrite newer data. Schedule-mode enablement and other immediate settings or
hardware controls remain separate APIs, not schedule-entry document edits.

Plugin demo creation is also a distinct operation. The tool's default
`recreate: false` preserves an existing edited demo. Explicit `recreate: true`
resets it from the current server template and discards edits, as its tool
description warns; it is not a draft update and does not carry a draft
precondition. The legacy demo REST action also resets existing demos. Reset
invalidates earlier page identity/revision, so an older native draft cannot
silently save over the replacement. Native clients must present reset as an
explicit destructive action, separate from saving a page draft.

Revision checks and dependent mutations share the owning locks. Cross-store
operations use settings → config → pages → collections → schedules order.
The contract relies on the existing one-process deployment with one live owner
per store; it does not add distributed locking for multiple API workers or
independent out-of-process file writers. Backup restore is not a transaction
across every file in the deployment.

## Rich page preservation

`page-document-v1` advertises preservation of JSON extension **values**, not a
byte-for-byte JSON representation or support for future rendering behavior.
Whitespace, key order, number spelling, and known model normalization are not
part of the guarantee. Native editors should also require `page-revision-v1`
and retain the original revision when using this document contract.

| Location/action | Contract |
| --- | --- |
| Unknown top-level page fields | Retained on read, unrelated updates, create, share, and import; sparse updates do not edit arbitrary unknown top-level keys |
| Rows and line metadata | Unknown JSON extensions survive unrelated edits and a replacement that carries those extensions |
| Canvas, area, content, supported shape fields | Page-scoped models retain extensions, explicit nulls, and omitted optional canvas fields |
| Supplied list fields | Replace the complete field; no implicit merge by index or guessed element identity |
| Nullable content fields | Explicit null follows that field's existing removal/reset semantics; omission leaves it unchanged |
| Identity, timestamps, revision/protocol, demo provenance | Server-owned; create/import/update cannot claim them as editable author content |
| Unknown shape types or invalid known geometry | Rejected; retained extensions do not bypass existing validation |
| Standalone/plugin canvas DSL | Remains strict; page document tolerance does not broaden plugin rendering contracts |

An editor replacing a nested list must carry all fields it intends to retain,
including extensions it does not understand. Omitting an element from a
replacement removes it; preservation never resurrects it. Opaque extension
strings do not acquire template execution or plugin-fetch behavior. Non-JSON
objects and non-finite extension numbers are rejected.

The page store also retains unknown outer document members while keeping the
schema version check authoritative. A future unsupported schema must not be
made writable merely because known fields can be parsed. Supported schema
migrations continue to own changes to known persisted semantics.

## Native work after this merge

These server contracts enable the clients; they do not implement their screens
or establish App Store readiness. Rich visual authoring, collection/schedule
editors, OAuth browser presentation, draft reconciliation, accessibility,
adaptive layouts, and device testing remain native implementation work. A
successful content save acknowledges storage, not hardware delivery. Explicit
preview and board controls retain their own target and compatibility checks.

The original page foundation and its historical verification are retained in
[ios-api-access.md](ios-api-access.md). The implementation checklist is
[native-client-readiness-plan.md](native-client-readiness-plan.md).
