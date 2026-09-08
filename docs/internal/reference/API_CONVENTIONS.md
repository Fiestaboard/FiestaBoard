# REST API Conventions

Status: adopted 2026-09 (issue #1766, umbrella #1849). Applies to every new
endpoint immediately, and to existing endpoints as their domain is extracted
into a router. The 2026-08 audit found three sibling create endpoints with
three response shapes, zero 201s, `response_model` on 19 of 179 endpoints,
~30 failure responses served as HTTP 200, and both string and dict
`HTTPException.detail` payloads — these rules exist so that never regrows.

## Enforcement: the conventions ratchet

These rules are a build failure, not a document.
`tests/test_api_conventions_ratchet.py` checks four of them against the live
route table on every test run:

| Rule id | What fails the build |
| --- | --- |
| `response_model` | A route with no `response_model=` |
| `no_200_on_failure` | A `return` inside an `except`, or a `{"success": false}` / `{"status": "error"}` / `{"valid": false}` body on a route that answers 2xx |
| `typed_body` | A request body parameter annotated `dict`, `dict[str, Any]`, or `Any` |
| `declared_errors` | A route that declares no error status (4xx or 5xx) in `responses=` |

It is a **ratchet**: it only checks domains listed in
`tests/conventions_manifest.json`, and that list only grows.

```json
{
  "converted_domains": ["collections", "plugins"],
  "exceptions": [
    {
      "route": "POST /plugins/{plugin_id}/options/{options_id}",
      "rule": "no_200_on_failure",
      "reason": "Returns the last good options with an error field while a form is still being filled in; a 4xx would blank the user's in-progress form."
    }
  ]
}
```

**`declared_errors` and 503-only routes.** The rule asks for *an error
status*, 4xx or 5xx, so a route whose only failure is a dependency outage
declares its `503` and is done — no manifest exception needed. It was
originally written as "a 4xx", which would have cost seven `/plugins` routes
an exception apiece documenting a client error they cannot raise; the rule
was widened rather than the exceptions accepted. What it still refuses is a
route that documents *no* failure at all.

**Opting a domain in.** Append the domain's router tag (the `<domain>` in
`APIRouter(tags=[<domain>])`) to `converted_domains` — in the same PR that
converts it, not before. The recommended order is to add it *first*, capture
the four failures, and put that output in the commit body as the fail-first
evidence for the conversion.

**Recording an exception.** Add one `{"route", "rule", "reason"}` entry per
excused route+rule pair. `route` is `"METHOD /path"` exactly as the app
serves it; `rule` is one of the four ids above; `reason` explains why the
convention is wrong *here*, in terms a reviewer can argue with. A stale or
mistyped entry fails the build rather than silently excusing nothing: the
manifest test rejects unknown rule ids, duplicate pairs, routes the app does
not serve, and exceptions whose domain is not in `converted_domains`.

**Dead exceptions fail the build.** The manifest test re-runs each rule's own
checker against the route the exception names, and rejects the entry when the
rule already passes. An exception that excuses nothing is not harmless: it
exempts that route from the rule *forever*, so a later regression on it goes
unreported. Widening `declared_errors` from "a 4xx" to "any 4xx or 5xx" left
eleven of these behind — deleting `responses=` from `GET /cache-status` kept
the ratchet green until they were removed. When a rule is widened, delete the
exceptions it obsoletes in the same commit; the validator will name them.

**Where the rules are ambiguous, the ratchet flags.** A `return` inside an
`except` is reported even when it is deliberate, because a checker that
guesses is a checker nobody trusts. The cost of a false positive is one
manifest entry; the cost of a false negative is a shipped 200-on-failure.

## Response shapes

- **Bare bodies.** Return the resource (or list) itself — no `{"status":
  "success", "data": ...}` envelopes. `{"status": ...}` wrappers on existing
  endpoints are grandfathered until their domain's conventions pass; new
  endpoints never add one. The one endpoint that keeps its wrapper past its
  own conventions pass is `POST /plugins/{id}/receive`: it is a webhook target
  for third-party systems this repo does not control and cannot update in
  lockstep, so "deprecation, never deletion" applies to it literally.
- **Derived or masked payloads get their own wire model.** Aliasing the
  storage model (`CollectionResponse = Collection`) is honest only when the
  two really are the same object. `GET /plugins/{id}` assembles its body from
  four collaborators and masks every secret in it, so it declares
  `PluginDetail` instead — conflating the masked shape with the stored shape
  is what let the #1743 masking regression through.
- **`response_model` on every endpoint.** The route declares its Pydantic
  response model; no untyped `dict` returns. This is what keeps the TS client
  (`web/src/lib/api/`) honest — `/check-types` compares against these models.
- **Typed request models.** No `request: dict` parameters. Validation errors
  are FastAPI's standard 422.

## Status codes

- Create → **201** with the created resource.
- Delete → **200** with the deleted resource id, or **204** with no body —
  pick per domain and stay consistent within it.
- **Failures are never 200.** A handler must not answer an error with
  `{"success": false}` and HTTP 200. Client errors are 4xx, server errors
  5xx.
- **Probe endpoints: one narrow exception.** An endpoint whose declared job
  is to *report a verdict about something else* — `POST /config/board/test`,
  `POST /config/board/enable-local-api` — answers 200 when the probe ran, even
  when the verdict is "the board refused this key". The verdict is the payload
  the caller asked for, not a transport failure. Three conditions make that
  legitimate, and all three are required:
  1. the 200 body is a declared `response_model` (`BoardTestResponse`,
     `EnableLocalApiResponse`), never an ad-hoc dict;
  2. the failure originated **upstream** — the board, or the network to it;
  3. anything the server rejected *before* probing (missing credential,
     malformed host, an SSRF-guard refusal) is a real 4xx, and anything
     unanticipated is a 5xx.

  `POST /schedules/validate` is the same shape of thing: an inconsistent set
  of schedules is the verdict the caller asked for, served 200 as a declared
  `ScheduleValidationResult`.

  The two `/config` probes no longer carry a `no_200_on_failure` exception.
  `no_200_on_failure` walks the **handler's own AST**, and when the layering
  ratchet moved these verdict bodies into `src/config_api/service.py` the rule
  stopped seeing them — a dead exception, which `validate_manifest` fails the
  build on. Nothing about the contract changed, and nothing is unguarded: the
  status/verdict pairs are pinned by value in `tests/test_config_contract.py`
  and `tests/test_status_code_correctness.py`. Note the general lesson — moving
  logic *out* of a handler silently retires this ratchet's coverage of it, so
  the value pins have to exist first.

  Without (1) a generic client cannot tell the verdict from a success, which
  is exactly the masking bug this rule replaced (#1887). `POST
  /debug/test-connection` deliberately does *not* qualify: it has no verdict
  body — no error class, no troubleshooting steps — so an unreachable board
  there is a 503 and an unexpected error is a 500.
- Missing resource → **404**; conflict (duplicate id, env-pinned resource) →
  **409**; feature unavailable / dependency down → **503**.

## Error contract

One shape everywhere: FastAPI's `{"detail": <string>}`. When structured
detail is genuinely needed (validation lists, per-field errors), `detail` is
an object with a `message` string plus named fields — never a bare string in
one endpoint and a dict in its sibling. No stringified tracebacks in any
response (CodeQL also enforces this).

**Declare it with `errors()`, never a hand-written dict.** `src/api_errors.py`
is what attaches `model=ErrorResponse` to each declared code (except 422, see
below); a domain that hand-rolls its `responses=` publishes the codes with
*no* body in the OpenAPI schema, and its inline descriptions drift from the
canonical text. The `system` domain did exactly that on four routes — fifteen
declarations, none with a model — because `errors()` had no 500 entry and
raised for it. It has one now: a **deliberately raised** 500, not an unhandled
error.

**422 belongs to FastAPI.** It is the code FastAPI generates for schema
validation, and its body is a *list* of errors, not `{"detail": <string>}`. A
hand-raised semantic rejection of a body that already passed validation is a
**400** — declaring 422 for it would publish the wrong model for the real
validation error on the same route. `errors(422)` therefore publishes
`HTTPValidationError` (the list shape), not `ErrorResponse`: attaching
`ErrorResponse` to 422 overrode FastAPI's own model with one that lied about
the shape (#1923).

## Routers and services

- Every domain lives in `src/<domain>/routes.py` (`APIRouter`, OpenAPI
  `tags=[<domain>]`) with orchestration in `src/<domain>/service.py`;
  `src/api_server.py` is an app factory that mounts routers.
- Routes never touch another object's `_private` members — that is the
  service's job (see `PluginService.mask_config` / `clear_update_status` for
  the pattern).
- **Services raise domain errors; routers map them to status codes.** A
  service that raises `fastapi.HTTPException` has an opinion about HTTP it is
  not entitled to, and it forces every non-HTTP caller (MCP tools, chat ops,
  background tasks) to import a web framework to catch its failures. The
  pattern: define the domain's exceptions in `src/<domain>/errors.py` with no
  status codes on them, and put one `_STATUS_BY_ERROR` table in
  `src/<domain>/routes.py` (see `src/plugins/`). `PluginService` was the one
  service that broke this — 25 raise sites, fixed in the plugins slice.
- During extraction, moved handlers resolve api_server-patched names at call
  time (the `src/mqtt/commands.py` pattern) so existing test patch targets
  stay live. Follow-up: migrate patch targets to the service modules, then
  retire the call-time seams.

## Deprecation, never deletion

A reachable endpoint that must change shape or move keeps serving its old
contract through a deprecation window:

- Response headers: `Deprecation: true` and
  `Link: </successor/path>; rel="successor-version"`, plus `Sunset: <date>`
  once a removal release is chosen.
- The successor ships first; the deprecated route becomes a shim over the
  same service (see `GET/PUT /config/board`).
- Duplicate endpoints (the audit found 3× cache, 2× install, 3× "what's on
  the board") are collapsed the same way: one canonical route, shims with
  headers on the rest.
- Only provably unreachable code is deleted outright (#1747-class: no route
  decorator, no dynamic registration, no importer).

**A route with no consumer is still not deleted.** The last slice audited
thirteen platform routes that serve one plugin each — the shape `CLAUDE.md`
forbids in `src/` — by grepping `web/src`, `web/tests`, the bundled plugins
and every sibling plugin repo. Eleven had no caller of any kind, and two of
those eleven are published as API reference in shipped plugin SETUP guides, so
an integration this repo cannot see may still call them. They are marked
`deprecated=True` in the OpenAPI schema and tracked for removal in #1915;
they are deliberately **not** in `converted_domains`, because re-shaping a
response body we intend to delete buys a lockstep web change and nothing else.
"deprecation, never deletion" applies to unused routes too — "nothing in this
repo calls it" is not the same claim as "nothing calls it".

Since then those eleven serve the notice on the wire rather than only in the
OpenAPI schema. Every one sends `Deprecation: true` and
`Sunset: Tue, 01 Dec 2026 00:00:00 GMT`; the ten replaced by the generic
remote-options endpoint also send a `rel="successor-version"` link to
`/api/plugins/<plugin_id>/options/{options_id}`, with the plugin id filled in
and `options_id` left as a template because only the plugin's own manifest
declares it. `/transit/cache/status` has no successor and sends no link. The
date lives in `DEPRECATED_ROUTES_SUNSET` in `src/api_server.py`, and
`tests/test_deprecated_route_headers.py` pins which route points where.

A quarter, not "two releases": FiestaBoard cuts a minor release every few
days, so a release count is not a window an outside integrator can plan
against — and callers this repo cannot see are the entire reason these routes
still exist.

### The second cohort: what `/v1` supersedes

The same rule was then applied to the routes `/v1` replaced. #1934 moved every
web-client call `/v1` supersedes onto `/v1` and left **33** internal endpoints
with no product caller; #1936 closed five of the ten gaps that migration found.
**25 of the 33** carry the notice from #1941, on the same clock
(`Sunset: Tue, 01 Dec 2026 00:00:00 GMT`) — one appliance, one removal date,
because two countdowns a few weeks apart means an integrator has to track both
to learn when their script stops working. The cohort is
`SUPERSEDED_BY_V1` in `src/api_deprecation.py` and
`tests/test_superseded_route_headers.py` pins it in both directions.

**The eight that were excluded are the reviewable half.** A
`successor-version` link is a promise that following it loses nothing, so a
route whose v1 equivalent still drops a field is *not* superseded and does not
get one:

| Not deprecated | What its v1 equivalent still drops |
|---|---|
| `POST /pages/{id}/send` | `paused` and `target`; a paused board is a 409 on v1, not a 200 that says so |
| `POST /displays/{type}/send` | nothing in `POST /v1/boards/{b}/message` accepts a plugin id at all |
| `GET`/`PUT /schedules/enabled` | both answer for the *install* when no `board_id` is given; `GET`/`PATCH /v1/boards/{board}` has no board-less form, and the write 404s where these fall back to the global mirror |
| `GET`/`PUT /schedules/default-page` | same |
| `GET /displays` | `source`; and it 503s where this answers 200 with an empty list |
| `POST /settings/board/{id}/pause` | the embedded `board_settings` block — `BoardDetail` deliberately carries no credentials, tiles, colour or transport fields |

**Known limitation of the mechanism, shared with the first cohort.**
`deprecation_notice` stamps the `Response` FastAPI injects into the handler,
and FastAPI merges that object's headers only into a response built from a
returned value. A route that raises `HTTPException` is answered from a fresh
response and the notice is dropped, so a caller who only ever sees 4xx never
sees it. Pinned by
`test_a_refusal_carries_no_notice__inherited_limitation` rather than left to be
rediscovered as a bug.

## Identifiers

- Resource ids are validated against reserved route words so
  `/plugins/{id}` cannot be shadowed by literal segments
  (`updates`, `registry`, `install`, ...). Each router owns its reserved
  list next to its routes.

### `board_id` validation: writes 404, reads fall back

Decided 2026-09 with #1888. The asymmetry is deliberate and it is the
inconsistency-of-record, so read it before "fixing" either half.

- **Writes 404.** Any handler that persists something scoped to a board
  calls `_require_board(board_id)` (`src/board_guards.py`) — the single place
  the "unknown board" verdict is made. It resolves the settings service
  through `src.board_guards.get_settings_service`, so **one** stub steers the
  board verdict for every domain. There was briefly a second implementation,
  `require_board(board_id, settings_service)` in `src/boards.py`, taking the
  service as a parameter; two seam designs for one identical lookup meant a
  fixture could stub `src.board_guards` and steer nothing, so it is gone.
  Writing state bound to a board that does not exist is invisible until
  something else trips over it: the four schedule write endpoints used to
  store a phantom default page, a no-op that reported
  `{"status": "success"}`, and schedules parented to nonexistent boards.
- **Reads fall back.** `GET /schedules` answers `[]`, `GET /schedules/enabled`
  answers `false`, `GET /schedules/default-page` answers the global default,
  and their siblings behave the same way. This is not an oversight:
  1. a read cannot corrupt anything, so the worst case is a caller shown the
     safe empty answer;
  2. board-scoped polling legitimately races board deletion — one tab
     removes a board while another is mid-poll for it — and 404ing there
     turns a benign race into an error toast for the user;
  3. the fallback answer ("no schedules", "not enabled") is *correct* for a
     board that does not exist, whereas a write's fallback ("saved!") is a
     lie.

  `board_id=*` on `GET /schedules` stays a documented wildcard, not an id.

If reads are ever made strict, they must all change together and the
polling clients must be updated in the same PR.

Two `SettingsService` setters — `set_paused` and `set_active_page_id` —
also raise `ValueError` on an unknown board. Both are **unreachable with an
unknown board over HTTP today** (every route reaching them validates first
or 404s on its own path parameter); the raise is defense in depth so a
future caller cannot recreate the phantom write.

## Zero-regression mechanics (how a conventions pass lands)

1. Record the domain's **response-shape golden** from current behavior
   (`tests/test_response_shape_goldens.py`, `RECORD_RESPONSE_GOLDEN=1`).
2. Extract the router as a **pure move** — golden diff must be empty.
3. Apply conventions in a separate commit — golden updated deliberately,
   old shapes still served under deprecation headers where any client could
   depend on them.
4. The route-inventory golden (`tests/test_route_inventory.py`) changes only
   with an explanation in the same commit.
5. Add the domain to `converted_domains` in
   `tests/conventions_manifest.json` (see *Enforcement* above) so the pass
   cannot silently unwind later.

## Streaming endpoints

`POST /pages/ai/chat` is the one route in the app that answers with a
`StreamingResponse` rather than a document, and it is the shape to copy if
another is ever added. A `response_model` cannot describe it — FastAPI would
either publish a JSON schema for a body that is never JSON, or coerce the
response and buffer the stream, which defeats the point of streaming. So:

- declare the media type on the 200 (`"content": {"text/event-stream": ...}`)
  with a description naming every event the stream can emit;
- keep a **registry** of the event names mapped to the Pydantic model
  describing each one's payload (`CHAT_STREAM_EVENTS` in
  `src/ai/page_routes.py`). That registry is what the missing
  `response_model` would have been, so it only earns its keep if something
  holds it to the wire: one contract test validates real frames against it,
  another walks the literal `{"event": ...}` dicts in the streaming source
  and asserts the two sets are equal, so a new event type cannot ship
  undocumented;
- record the `response_model` exception in the manifest, pointing at the
  registry.

Failures divide by *when* they happen. Anything the server rejects before the
200 is on the wire is an ordinary JSON error response and is declared in
`responses=` as usual. After the headers are sent the status code is already
spent, so the only way to report a failure is a terminal event in the stream
itself — which is why an `error` frame at HTTP 200 is not a
`no_200_on_failure` violation.
