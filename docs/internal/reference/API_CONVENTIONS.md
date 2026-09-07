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
