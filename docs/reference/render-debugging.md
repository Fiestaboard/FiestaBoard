---
description: "Inspect formula execution and trace rendered board cells back to their template sources."
keywords: [FiestaBoard API, formula trace, source map, template debugging]
---

# Inspect a template render

The page editor and native clients can request a formula execution trace and a
source map from `POST /templates/render`. Inspection uses the same preview
context and pinned clock as the rendered board. It does not send to a display.

```json
{
  "template": ["TEMP {{= weather.temperature + 1 }}"],
  "debug": {
    "trace": {"line": 1, "start": 5},
    "source_map": true
  },
  "preview": {
    "values": {"weather.temperature": 20},
    "data": "cached"
  }
}
```

`debug` is optional. Without it, the response is unchanged. With it, the
response includes the existing `diagnostics` values and line overflow report,
plus a `debug` object. Omit `trace` to request only the map; omit `source_map`
to request only the trace. Unknown inspection options are rejected.

## Select a formula

Use a formula's `line` and `start` from `diagnostics.formulas`. Lines are
1-based. Offsets are zero-based Unicode code points, with an exclusive end;
JavaScript clients must convert UTF-16 editor offsets when supplementary
characters precede the selection. The selection starts at the opening `{{`,
not the formula body. An invalid selection returns 422.

`debug.trace` contains the selected formula's H5 fields (`line`, `start`,
`end`, `source`, `value`, `value_truncated`, `error`, `error_at`, `message`),
plus `events` and `truncated`. The `source` body excludes braces and surrounding
whitespace. Event spans use offsets within that body.

Events represent actual evaluation calls. Each has an `id`, nullable `parent`,
`kind`, `label`, `start`, `end`, `value`, `value_truncated` and nullable `error`.
Parents are listed before children; their values are completed after their
children run. Loop iterations have distinct event IDs even when their source
spans are equal. Short-circuited operands have no events. Functions retain the
language's existing eager or lazy argument behavior.

Event values are strings limited to 128 code points. Lists and objects are
summarized as `list(N)` and `dict(N)` without exposing their contents. At most
256 events are retained. `truncated` means some executions were omitted;
`value_truncated` separately identifies a shortened value. Evaluation continues
when event recording fills up. Syntax errors have no execution events and
retain their error position and message.

## Find a cell's source

`debug.source_map` contains `rows`, `cols`, `sources` and `cells`. For a board
cell at zero-based `[row][col]`, look up `cells[row][col]` in `sources`. A null
cell is generated layout padding. Each source contains `line`, `start`, `end`
and `kind` (`literal`, `variable`, `formula`, `fill`, or `markup`).

A literal cell points to its authored code point. A substituted value points
to its whole variable or formula atom, including any filters. Fill cells point
to the fill directive. Standalone color tiles and icons point to their markup
atom. Nested color spans preserve the source of their inner text. Wrapped and
spilled cells keep their origins; clipped text has no visible cell. All rows
have exactly `cols` entries, including padding.

The map records the source of the rendered cell, not a list item's index.
For example, every row emitted by `FOREACH` points to its formula atom; request
that formula's trace to inspect execution.

`debug.source_map_status` is `complete`, `limit`, or `not_requested`.
A `limit` map is null: provenance tracking exhausted its budget, while the
render and selected formula trace remain available. Clients should hide cell
source navigation for that response instead of guessing origins.

## Limits and supported render modes

Inspection requires a list template. Pixel canvas layouts and live rendering
reject `debug` with 422. Existing non-debug rendering remains available for
those modes.

A debug request allows at most 64 template lines, 64 formulas, 16,384 template
code points and 4,096 board cells. A selected trace body allows at most 4,096
code points. Oversized request fields return 422 before plugin data is fetched.
When the request uses a configured board's geometry instead, a board exceeding
4,096 cells returns 400 before plugin data is fetched.
Provenance has a cumulative 262,144-character tracking budget. Formula text,
steps and deadlines remain subject to the existing evaluator limits.

Sample data, simulated missing data, cached plugin data and `preview.at` work
as on other preview renders. They are request-local and never persisted. An
empty template still returns an all-padding source map when requested.
