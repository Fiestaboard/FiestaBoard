# H7: bounded formula trace and cell origins

Status: accepted for implementation under the autonomous H7 handoff.
Consumers: web 2.10 and the native editors. Builds on H5, H6 and S2.

## Decision

Extend `POST /templates/render` with an optional `debug` object. Preserve
`diagnostics: bool`, its existing fields, and responses when debug is absent.
Debug implies H5 diagnostics and uses H6's same request-local context and clock.

```json
{"template":["TEMP {{= weather.temperature + 1 }}"],
 "debug":{"trace":{"line":1,"start":5},"source_map":true}}
```

`trace` selects one formula by its H5 location (1-based template line and
0-based opening-brace offset). Omit it when only the map is needed. Selection
must identify a formula or return 422. Offsets are Unicode code points, not
UTF-16 units. `source_map` defaults to false. Unknown debug keys are rejected.
The response's optional `debug` object has `trace` and `source_map`, each null
when not requested. There is no new route or authorization scope.

Debug accepts list templates only. A bare string has no board geometry/layout
contract. Pixel canvases and `/templates/render/live` reject debug with 422:
this inspection operation must never send to a board. These restrictions
apply only to the new flag; existing rendering and H5/H6 behavior remains.
Empty list templates return an all-padding map when requested.

## Trace

The trace is collected from the selected formula's actual evaluation, never
by re-evaluating its nodes. The trace object contains the selected `line`,
`start`, `end`, its `source`, final `value`, `error`, and `events`, plus
`truncated`. Existing H5 result limits apply to the final value.

Each event has `id`, nullable `parent`, `kind` (literal, variable, unary,
binary, call), `label`, `start`, `end`, `value`, `value_truncated`, and nullable
`error`. Event spans refer to the stripped `source` body. IDs are allocated
on entry in execution order, with results filled on exit. Parentheses may
be included in a node span. Repeated loop evaluations get distinct IDs but
share source spans. Skipped short-circuit operands produce no event. Eager
function arguments remain eager; tracing never changes language semantics.

Record at most 256 events. Reserve parent/root slots before children so a
truncated trace still contains the completed root. Labels and scalar value
previews are limited to 128 code points. Collections use type/count summaries
without traversal or serialization. Errors keep their codes. Parse errors
have no execution events and use the H5 error details. Restore recorder state
on every exit, including failure and concurrent requests.

S2's per-formula and shared render step/deadline budgets stay authoritative.
Trace recording does not reset or bypass them. Reaching the recording cap
stops recording, not evaluation. A time/step exhaustion remains a formula
error even inside IFERROR. Test deadline behavior with an injected clock;
use generous real-time checks only as a secondary regression signal.

## Cell source map

`source_map` contains `rows`, `cols`, `sources`, and `cells`. `cells[row][col]`
is a zero-based index into `sources`, or null for generated layout padding.
Every row has exactly `cols` entries and there are exactly `rows` rows.
Each source is `{line,start,end,kind}` with half-open authored template offsets;
kind is literal, variable, formula, fill, or markup. A substituted value,
including filters and automatic color tiles, points to its entire authored
atom. Literal text points to its authored span. Extended markup preserves its
source through wrapping, splitting, clipping and span serialization. Formula
output points to its formula atom, including each FOREACH output row; clients
can then request that formula's trace. Layout padding has no authored source.

Carry provenance alongside actual rendered text through substitutions and
layout; never infer sources by matching output text (repeated values are
ambiguous). Intern source records and keep at most one cell ID per board cell.
Use compact source runs internally rather than one object per character.
Fill cells point to the fill directive, while alignment and implicit blank
rows are null. Clipped/covered/beyond-board text has no output cell.

## Request and memory budgets

Debug requests are capped at 64 template lines, 16,384 total template code
points and 4,096 board cells. Reject over-budget requests with 422 before
context fetch/evaluation. Trace input is additionally capped at 4,096 formula
body code points. Per-render provenance work has a fixed 262,144-character
intermediate tracking budget; on exhaustion return `source_map: null` and a
`source_map_status: "limit"` rather than guessing origins or failing an
otherwise valid render. Otherwise status is `complete` or `not_requested`.
No context dumps or repeated source/value text appear in cell records.

## Approaches considered

1. Selected debug on render (chosen): one bounded trace and independent map,
   shared preview/geometry/auth behavior, default and H5 contracts preserved.
2. Trace every formula whenever diagnostics is true: simpler request, but
   changes existing clients' payload/cost and spends a global trace cap before
   the selected formula may run.
3. Separate debug endpoint: clear boundary, but duplicates or refactors the
   existing preview/geometry machinery without a consumer benefit.

Jev selected option 1 with probability 0.87 (reported confidence 0.84), with
all three compatibility/evaluation/bounding requirements supported.

## Implementation and verification

Remove duplicate formula evaluation from debug rendering: reuse actual
outcomes for H5 values and the trace. Hidden H5 entries retain their existing
contract and are evaluated at most once per authored occurrence in the
request. Reuse outcomes for wrap measurements and overflow probes.

Tests cover default wire compatibility, request validation before fetching,
H6 sample/missing/clock isolation, errors and S2 exhaustion, bounded traces,
repeated identical atoms, nested markup, fill/alignment, variable wrap,
FOREACH spill/footer clipping, blank boards, unknown selection and concurrency.
Update OpenAPI models/generated reference, real-response contract fixtures,
and add a minor changeset. Run full pytest and ruff, then independent exact-head
Astra review and CI. No UI, release, merge or publishing changes are in scope.
