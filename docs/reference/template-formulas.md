---
sidebar_position: 6
description: "Reference for template expressions — the Excel-like inline formula language for FiestaBoard templates. Use IF/ELSE, math, and string functions in a single line."
keywords: [FiestaBoard templates, formula language, Excel formulas, IF ELSE template, template expressions, conditional template, inline expressions]
---

# Template Expressions

Template expressions are a small, Excel‑style formula language that runs inside a single
line of any FiestaBoard template. If you've ever written `=IF(A1>10, "hot", "ok")`
in a spreadsheet cell, you already know most of it.

It is designed for one job: **let you compute a value (text, number, color tile)
inline, without leaving the template, without writing Python**.

> **Why a new language?** A template line is a single cell. Sometimes you need
> "if it's raining, show an umbrella; otherwise show a sun" or "show the price
> in green when it's up, red when it's down". Template expressions give you a sandboxed
> way to express that logic without us shipping Turing‑complete code execution
> on the device.

## TL;DR

Anything inside `{{= ... }}` is a formula. Everything else in your template
works exactly as before.

```text
Temp: {{= weather.temperature }}{{= IF(weather.temperature > 80, " HOT", "") }}
```

renders as `Temp: 92 HOT` when it's 92°F, and `Temp: 71` when it's 71°F.

```text
{{= IF(stocks.AAPL.change >= 0, COLOR("green"), COLOR("red")) }} AAPL {{= FIXED(stocks.AAPL.price, 2) }}
```

shows a green tile + the price when AAPL is up for the day, a red tile when
it's down.

---

## Syntax basics

### Marker

A formula is anything between `{{=` and `}}`. Whitespace after `=` is allowed.

```text
{{= 1 + 1 }}              -> 2
{{=  UPPER("hi")  }}      -> HI
{{= weather.temperature }} -> 72
```

The plain variable form `{{plugin.field}}` and the color shortcut `{{red}}`
still work exactly as before. **You only opt in to formulas where you write
`{{= ... }}`.**

> **One restriction:** because `{` and `}` mark the boundaries of a formula,
> they cannot appear inside string literals. Use `COLOR("red")` instead of
> writing `"{63}"` directly.

### Literals

| Kind     | Examples                                  |
|----------|-------------------------------------------|
| Number   | `42`, `3.14`, `-5`, `.5`                  |
| String   | `"hello"`, `"line one\nline two"`, `"a\"b"` |
| Boolean  | `TRUE`, `FALSE`                           |
| Null     | `NULL` (renders as empty string)          |

Strings use double quotes only. Supported escapes: `\"`, `\\`, `\n`, `\t`, `\r`.

### Variables

Variables use the same dotted notation as plain `{{ }}` substitution:

```text
{{= weather.temperature }}
{{= stocks.AAPL.price }}
{{= home_assistant.sensor_outdoor_temp.state }}
{{= baywheels.stations.0.electric_bikes }}
```

A missing source, missing field, or out‑of‑range index produces a `#REF`
error, which propagates through the rest of the formula (so you can trap it
with `IFERROR` — see [Errors](#errors)).

### Operators

| Group         | Operators                                     | Notes                          |
|---------------|-----------------------------------------------|--------------------------------|
| Arithmetic    | `+`  `-`  `*`  `/`  `%`                       | numeric                        |
| Concatenation | `&`                                           | always returns string          |
| Comparison    | `=`  `==`  `!=`  `<>`  `<`  `>`  `<=`  `>=`   | `=` and `<>` are Excel aliases |
| Logical       | `AND`  `OR`  `NOT`  (also `&&`  `\|\|`  `!`)  | short-circuit                  |
| Grouping      | `( )`                                         |                                |
| Unary         | `+x`, `-x`                                    |                                |

Precedence, low to high:
`OR` → `AND` → `NOT` → comparison → `&` → `+ -` → `* / %` → unary → call/atom.

#### Coercion rules (the Excel‑ish parts)

- **Comparisons:** if both sides look numeric, they are compared as numbers
  (`"10" > "9"` is true). Otherwise they're compared as strings,
  case‑insensitively.
- **Arithmetic:** strings that parse as numbers are coerced (`"5" + 1 == 6`).
  Anything else produces `#VALUE`.
- **`&` (concat):** always coerces both sides to text.
- **Booleans in numeric context:** `TRUE` is `1`, `FALSE` is `0`.
- **Booleans rendered as text:** `Yes` / `No` (matching the rest of the
  template engine).

---

## Built‑in functions

Function names are case‑insensitive (`if(...)` and `IF(...)` are equivalent).
Custom user‑defined functions are intentionally **not supported**.

### Logic

| Function | Description |
|----------|-------------|
| `IF(cond, then [, else])` | Returns `then` if `cond` is truthy, else `else` (default: `""`). |
| `IFS(c1, v1, c2, v2, ..., [default])` | Returns the value for the first true condition; `default` is used if none match. Returns `#VALUE` if no match and no default. |
| `SWITCH(value, m1, r1, m2, r2, ..., [default])` | Returns the result whose match equals `value`. Comparison uses the same coercion as `==`. |
| `AND(a, b, ...)` | True if all args are truthy. Short‑circuits. |
| `OR(a, b, ...)` | True if any arg is truthy. Short‑circuits. |
| `NOT(a)` | Logical negation. |
| `IFERROR(expr, fallback)` | Returns `fallback` if `expr` evaluated to an error; otherwise the value. |
| `ISERROR(expr)` | `TRUE` if `expr` evaluated to an error. |
| `ISBLANK(expr)` | `TRUE` for `NULL`, empty string, or the missing-value sentinel `???`. (Errors propagate.) |
| `DEFAULT(expr, fallback)` | Returns `fallback` if `expr` is missing, blank, or an error; otherwise `expr`. |
| `COALESCE(a, b, c, ...)` | The first argument that isn't an error / `NULL` / blank. The n-ary version of `DEFAULT`; great for fallback chains. |

### Math

| Function | Description |
|----------|-------------|
| `ABS(x)` | Absolute value. |
| `ROUND(x [, n])` | Round to `n` decimals (default `0`). Banker's rounding. |
| `ROUNDUP(x [, n])` | Round **away from zero** to `n` decimals (Excel ROUNDUP). |
| `ROUNDDOWN(x [, n])` | Round **toward zero** to `n` decimals (Excel ROUNDDOWN). |
| `FLOOR(x)` | Round toward negative infinity. |
| `CEIL(x)` | Round toward positive infinity. |
| `INT(x)` | Truncate toward zero. |
| `POWER(base, exp)` | `base` raised to `exp`. Returns `#NUM` for complex/overflow results. |
| `SQRT(x)` | Square root. `#NUM` for negatives. |
| `MIN(a, b, ...)` / `MAX(a, b, ...)` | Smallest / largest. |
| `SUM(a, b, ...)` / `AVG(a, b, ...)` | Sum / arithmetic mean. |
| `MOD(a, b)` | `a` modulo `b`. `#DIV/0` if `b == 0`. |
| `SIGN(x)` | `-1`, `0`, or `1`. |

### Text

| Function | Description |
|----------|-------------|
| `UPPER(s)` / `LOWER(s)` | Case conversion. |
| `PROPER(s)` | Title-case each word. Apostrophes stay inside the word (`don't` → `Don't`). |
| `TRIM(s)` | Strip leading/trailing whitespace. |
| `LEN(s)` | Length in characters. |
| `LEFT(s, n)` / `RIGHT(s, n)` | First/last `n` characters. |
| `MID(s, start, length)` | Substring. **`start` is 1‑indexed**, like Excel. |
| `FIND(needle, haystack [, start])` | Case-sensitive position (1-indexed). Returns `#VALUE` if not found. |
| `SEARCH(needle, haystack [, start])` | Case-insensitive position. Returns `0` if not found (so `IF(SEARCH(...) > 0, ...)` works). |
| `CONCAT(a, b, ...)` | Concatenate (alternative to `&`). |
| `REPLACE(s, find, repl)` | Replace all occurrences. |
| `REPT(s, n)` | Repeat `s` `n` times. Capped at 1024 to prevent runaway memory (`#NUM` if exceeded). |
| `CONTAINS(s, sub)` | `TRUE` if `s` contains `sub`. |
| `STARTSWITH(s, p)` / `ENDSWITH(s, p)` | Prefix/suffix test. |
| `PAD(s, w)` | Right‑pad to `w` chars (truncates if longer). |
| `PADLEFT(s, w)` | Left‑pad to `w` chars with spaces. |
| `ZEROPAD(s, w)` | Left‑pad to `w` chars with zeros (e.g. `ZEROPAD(1, 2)` → `"01"`). A leading `-` sign is preserved (`ZEROPAD(-1, 3)` → `"-01"`). Values longer than `w` are returned unchanged. |
| `CENTER(s, w)` | Center within `w` chars. |

### Arrays

Some plugins expose a **list** of things rather than a single value — today's
games, the next few departures, a five-day forecast. You can still reach one
item by index (`{{transit.stops.0.eta}}`), but these functions let you ask how
many there are and lay them out without writing a line per possible item.

| Function | Description |
|----------|-------------|
| `COUNT(array)` | How many items the array currently holds. `#VALUE` if the value isn't an array. |
| `AT(array, index [, field])` | The item's `field` at a zero-based `index`. **Blank, not an error**, when the index or field isn't there — so you don't need an `IF` around every line. |
| `FOREACH(array, rowExpr [, limit])` | One board row per item. See below. |
| `FILTER(array, condition)` | The items whose `condition` is true. |
| `SORT(array [, field] [, "desc"])` | The array sorted by `field` (omit `field` for a list of plain values). |
| `SLICE(array, start [, count])` | A window of the array. |
| `JOIN(array, sep [, field])` | Items joined into one line of text. |
| `SUMOF` / `AVGOF` / `MINOF` / `MAXOF` `(array [, field])` | Aggregate one field across every item. |

An array is a value you pass **between** functions — it can never be printed
directly. `{{= mlb.games }}` renders `#VALUE`; use `COUNT`, `AT`, `JOIN` or
`FOREACH`.

#### `FOREACH` — one row per item

`FOREACH` is the only function that produces **more than one line**. It
evaluates `rowExpr` once per item and returns the rows joined by newlines,
which the renderer then spreads down the board — exactly how a `|wrap` line
overflows into the rows beneath it.

```text
SCORES ({{= COUNT(mlb.games) }})
{{= FOREACH(mlb.games, item.team1 & " " & item.score1, 4) }}
```

On a flagship that renders as:

```text
SCORES (3)
SF 4
NY 1
CHC 3
```

Three rules worth knowing:

- **Leave the rows below it empty.** `FOREACH` fills them.
- **Always pass a `limit`.** Without one, a plugin that suddenly returns 40
  items will run off the board. Pick a number that fits the rows you left.
- Inside `rowExpr`, **`item`** is the current item and **`index`** its position
  starting at 1. `item.field` reads a field; for an array of plain values
  (numbers, strings), `item` *is* the value.

Anything that returns an array composes in front of it:

```text
{{= FOREACH(SLICE(SORT(FILTER(mlb.games, item.final), "score1", "desc"), 0, 3), item.team1 & PADLEFT(item.score1, 3)) }}
```

— the three highest-scoring finished games, biggest first.

### Dates and times

Dates are values, like numbers. `NOW()` and `TODAY()` read the clock in your
board's configured timezone; `DATE()` parses the ISO strings plugins expose.

| Function | Description |
|----------|-------------|
| `NOW()` | Current date and time. |
| `TODAY()` | Midnight today. |
| `DATE(text)` | Parse `2026-12-25` or `2026-12-25T08:15:00`. `#VALUE` if it isn't a date. |
| `YEAR` / `MONTH` / `DAY` / `HOUR` / `MINUTE` `(d)` | One part, as a number. |
| `WEEKDAY(d)` | Day of week, **Monday = 1** through Sunday = 7. |
| `DATEDIFF(start, end [, unit])` | Whole units from `start` to `end`; negative when `end` is earlier. `unit` is `days` (default), `seconds`, `minutes`, `hours`, `weeks` or `months`. |
| `DATEADD(d, amount [, unit])` | Shift a date. Negative `amount` goes back. Adding months clamps to the month's last day (Jan 31 + 1 month = Feb 28). |
| `FORMATDATE(d, pattern)` | Format with `YYYY`, `YY`, `MMM`, `MM`, `DD`, `ddd`, `HH` (24h), `hh` (12h), `mm`, `ss`, `AP`. Anything else is literal text. |

```text
{{= DATEDIFF(TODAY(), DATE(launch.day)) }} DAYS TO GO
{{= FORMATDATE(NOW(), "ddd hh:mm AP") }}
{{= IF(HOUR(NOW()) >= 17, "EVENING", "DAY") }}
```

Every date function in one render sees the same instant, so a line can't
disagree with the line above it.

### Reuse

| Function | Description |
|----------|-------------|
| `LET(name, value, ..., body)` | Compute `value` once, then use `name` inside `body`. Takes several name/value pairs; a later value may use an earlier name. |

```text
{{= LET(done, FILTER(mlb.games, item.final), COUNT(done) & " FINAL: " & JOIN(done, " ", "team1")) }}
```

Names bound by `LET` exist only inside its `body`.

### Conversion / formatting

| Function | Description |
|----------|-------------|
| `TEXT(x)` | Convert to string using the engine's standard rendering. |
| `NUM(x)` | Convert to number. `#VALUE` on failure. |
| `FIXED(x [, n])` | Format with `n` decimals (default `2`). Returns a string. |
| `SPLIT(text [, sep])` | Split text into an **array** (default separator: whitespace). Pairs with the array functions. |
| `REGEXMATCH(text, pattern)` | `TRUE` if the pattern matches. |
| `REGEXEXTRACT(text, pattern [, group])` | The first match, or a capture group. Blank when nothing matches. |
| `REGEXREPLACE(text, pattern, repl)` | Replace every match. |

Patterns are limited on purpose, because a template render happens on the loop
that drives your board. Three rules, all reported as `#VALUE`:

- **At most 120 characters.**
- **No repeated group** — a `+`, `*` or `{n,m}` right after `(...)`. `(a+)+b`,
  `(a|a)+b` and `(a|ab)*c` all take exponential time, and only the first one
  advertises it; the alternation shapes look ordinary. The rule refuses every
  repeated group rather than guess, so a harmless `(ab)+` goes with them.
- **At most three `+`/`*`/`{n,m}` quantifiers.** `a*a*a*a*a*a*a*a*a*b` has no
  group to catch it — the cost is in the run of quantifiers itself.

Patterns a board actually needs fit comfortably: `([0-9]+)F / (\w+)`,
`^[A-Z]{3}-[0-9]+$`, `\s+`.

These rules are a list of shapes known to explode, not a guarantee. Python's
regex engine has no timeout, so a pathological pattern nobody has catalogued
could still make a render crawl. Keep patterns simple.

### Color (FiestaBoard‑specific)

| Function | Description |
|----------|-------------|
| `COLOR(name_or_code)` | Returns a single color tile marker. Accepts a color name (`"red"`, `"orange"`, `"yellow"`, `"green"`, `"blue"`, `"violet"`/`"purple"`, `"white"`, `"black"`, `"filled"`) or a numeric code `63`–`71`. |

The result of `COLOR(...)` is a `{63}`‑style marker that is treated by the
rendering pipeline as exactly one tile, so your alignment and word wrapping
behave correctly.

---

## Errors

When something goes wrong, an expression produces an **error value** that
short‑circuits the surrounding expression and renders as a tag. This matches
how Excel surfaces problems.

| Tag        | Means                                                 |
|------------|-------------------------------------------------------|
| `#REF`     | A variable, field, or array index could not be found. |
| `#VALUE`   | Wrong types (e.g., adding to a non-numeric string), or wrong number of arguments. |
| `#DIV/0`   | Division or modulo by zero.                           |
| `#NAME?`   | Unknown function name.                                |
| `#NUM`     | Numeric out of range or undefined (e.g., `SQRT(-1)`, `REPT` over the cap). |
| `#SYNTAX`  | Couldn't parse the formula. Includes the character offset where parsing stopped (e.g. `#SYNTAX:12`). |

### Editor validation

The page-editor's `validate_template` API now also parses every `{{= ... }}`
body and reports the same problems **before** you save the template, so you
don't have to wait for a render to find a typo. You'll see entries like:

- `Formula #SYNTAX: Unexpected character '@' at position 4`
- `Formula #NAME?: Unknown function: BOGUS`
- `Formula #VALUE: IF: expected at least 2 arg(s), got 1`
- `Formula #REF: Unknown source: misspelled_plugin`

### Trapping errors at render time

Trap errors with `IFERROR` so a missing data source can never break a board:

```text
{{= IFERROR(stocks.AAPL.price, "—") }}
```

`DEFAULT(value, fallback)` is shorthand for "use `value` unless it's missing,
empty, or errored":

```text
{{= DEFAULT(weather.condition, "n/a") }}
```

`COALESCE(a, b, c, ...)` walks a chain of fallbacks — the first one that
isn't an error, `NULL`, or blank wins:

```text
{{= COALESCE(home_assistant.weather.attributes.friendly_name,
             weather.condition,
             "n/a") }}
```

---

## Cookbook

### Conditional message

```text
{{= IF(weather.temperature > 90, "HEAT WARNING", "") }}
```

### IF / ELSE IF / ELSE chains

Two equivalent ways:

```text
{{= IF(weather.temperature > 90, "HOT", IF(weather.temperature > 70, "WARM", "COOL")) }}
```

```text
{{= IFS(weather.temperature > 90, "HOT", weather.temperature > 70, "WARM", "COOL") }}
```

`IFS` stays flat however many rungs you add; nested `IF`s don't.

### Switch on a discrete value

```text
{{= SWITCH(weather.condition, "Sunny", "CLEAR", "Rainy", "WET", "Cloudy", "CLOUD", "?") }}
```

A symbol like `{sun}` can't be the result: braces end a formula, so they can't
appear in a string literal. Put the symbol in the template around the formula,
or use `COLOR(...)` when a color tile will do.

### Color a value based on a threshold

```text
{{= IF(stocks.AAPL.change >= 0, COLOR("green"), COLOR("red")) }} {{= stocks.AAPL.symbol }} {{= FIXED(stocks.AAPL.price, 2) }}
```

### Combine values with `&`

```text
{{= weather.temperature & "F / " & weather.feels_like & "F feels" }}
```

### Format a number to one decimal

```text
{{= FIXED(weather.humidity, 0) }}%
```

### Provide a fallback when data is missing

```text
{{= IFERROR(home_assistant.sensor_garage_door.state, "unknown") }}
```

### Capitalize and truncate

```text
{{= UPPER(LEFT(weather.condition, 8)) }}
```

### Numeric width formatting (e.g., right-align in 4 columns)

```text
[{{= PADLEFT(stocks.AAPL.price, 4) }}]
```

### Compute a value

```text
{{= ROUND((weather.temperature - 32) * 5 / 9, 1) }}C
```

### Range/zone test

```text
{{= IF(AND(weather.temperature >= 65, weather.temperature <= 75), "perfect", "meh") }}
```

### Show a list, however long it is

```text
{{= COUNT(mlb.games) }} GAMES
{{= FOREACH(mlb.games, item.team1 & "-" & item.team2, 4) }}
```

No line-per-item guesswork: one row per game, up to four rows.

### Say so when the list is empty

```text
{{= IF(COUNT(transit.stops) = 0, "NO SERVICE", FOREACH(SLICE(transit.stops, 0, 3), item.eta & " " & item.name)) }}
```

### Countdown without a countdown plugin

```text
{{= DATEDIFF(TODAY(), DATE(launch.day)) }} DAYS
```

### A header row and a filtered body

```text
{{= LET(live, FILTER(mlb.games, NOT(item.final)), COUNT(live) & " IN PROGRESS") }}
{{= FOREACH(FILTER(mlb.games, NOT(item.final)), item.team1 & PADLEFT(item.score1, 3), 4) }}
```

---

## How it interacts with the rest of the template engine

A FiestaBoard template is rendered in passes. Expressions fit between color
normalization and plain variable substitution:

1. **Named color tags** (`{{red}} → {63}`).
2. **Formulas** (`{{= ... }}` evaluated and replaced with their result).
3. **Plain variables** (`{{plugin.field}}`).
4. **Symbols** (`{sun}`, `{rain}`, …).
5. Filters (`|wrap`, `|pad:N`, etc.), alignment, fill space, and tile counting
   run as usual on the final string.

Three practical consequences:

- `COLOR("blue")` produces the same `{67}` marker that `{{blue}}` would, so
  it interacts correctly with alignment, truncation, and word wrapping.
- A formula that returns several lines — which only `FOREACH` does — has each
  line laid into the board row below, and each gets its own alignment and fill
  space. That is the same machinery `|wrap` overflow uses, so a `FOREACH` needs
  the rows beneath it to be empty.
- A formula that returns a string containing `{{plugin.field}}` will have
  that variable resolved on the next pass — but this is rarely useful, and
  not recommended.

---

## What's intentionally not included

- **User‑defined functions and lambdas.** `LET` covers re‑use; defining your own
  functions is still out of scope.
- **`REDUCE` and general array formulas.** `FOREACH` walks an array and the
  `SUMOF`/`AVGOF`/`MINOF`/`MAXOF` family aggregates one, which covers what a
  board needs; arbitrary folds do not.
- **Side effects** (HTTP calls, time advance, mutations). Expressions are a
  pure expression language. Use plugins to bring data in.
- **Access to Python or the OS.** Formulas run in a small interpreter, not
  via `eval`. You can't import modules, read files, or escape the sandbox.

---

## Validation tips

- A bad formula renders as a short tag like `#SYNTAX` or `#REF` — look for
  those when something doesn't show up the way you expected.
- `ISERROR(x)` is handy in nested `IF`s when a piece of data may be unstable.
- The board is at most 22 columns wide on a flagship device and 15 columns
  on a Note (3 rows). Use `LEFT`, `PAD`, or `FIXED` to keep your output a
  predictable width.

---

## For editor / tool builders

`src.templates.expressions` exports a small public API designed for editor
integrations (autocomplete, in-line linting, function pickers):

| Symbol | Description |
|--------|-------------|
| `evaluate(expr, ctx)` → `str` | Evaluate a single formula; never raises. |
| `render_expressions(template, ctx)` → `str` | Replace every `{{= ... }}` in a template. Used by the engine. |
| `validate_expression(expr, known_sources=None)` → `list[ExpressionIssue]` | Static check: parse error, unknown function, arity mismatch, unknown source. Each issue has `code`, `message`, and optional `pos`. |
| `find_formulas(template)` → `list[(start, end, body)]` | Locate every formula block in a template — useful for rendering inline diagnostics. |
| `list_builtins()` → `tuple[str, ...]` | Sorted tuple of every built-in name. |
| `function_signatures()` → `dict` | `{ NAME: { category, signature, summary } }` for every built-in. Drives the function picker. |

`TemplateEngine.validate_template()` already calls `validate_expression`
under the hood, so editor validation is wired up "for free" for callers
that already use that endpoint.
