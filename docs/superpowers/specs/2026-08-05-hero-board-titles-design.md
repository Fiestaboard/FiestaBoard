# Hero board: name what you're looking at

**Date:** 2026-08-05
**Component:** `docs-site/src/components/HeroBoard/`

## Problem

The homepage hero cycles through six boards — dashboards and color art across
Flagship, Note, and three Note Array sizes. It captions each one with the
hardware only: `Flagship · 22 × 6`, `Note Array · 2 × 1`. A visitor can tell
what device they're looking at but never what it is *showing*. A diagonal
sunset gradient arrives with no explanation of what it is or why FiestaBoard
can draw it.

Separately, the rotation splits cleanly into "text boards" and "art boards".
Nothing demonstrates the more interesting case: data and color on the same
board.

## Design

### 1. Two-line caption

The caption becomes a title plus the existing device string:

```
      MORNING DASHBOARD      ← what you're looking at
      Flagship · 22 × 6      ← hardware, smaller and muted
```

`BoardConfig` gains a `title` field. The existing `label` field keeps its
current job (device and size) and its current styling — 12px mono, uppercase,
tracked, `--muted-foreground`. The title renders above it at 14px in
`--foreground`, same mono/uppercase/tracked treatment, so the pair reads as one
block with a clear hierarchy.

Both lines live in the existing `.caption` element and fade with it, so no
change to the fade logic. The caption is not a live region: it is plain text
that changes every few seconds, and announcing each change would spam screen
readers for content that is decorative on a marketing page.

**Layout shift:** the extra line makes the stage taller. `.stage`'s
`min-height` reserve and `.heroBoardFallback`'s matching reserve in
`src/pages/index.module.css` both grow by one line-height (~18px), keeping the
pre-hydration placeholder the same height as the mounted component.

### 2. Three data-and-color boards

FiestaUI's parser (`board-characters.ts`, `parseLine`) emits each `{color}`
token as a single cell and ignores closing tags, so a color tile can sit inline
anywhere in a row of text. That is enough to build hybrid boards with no
FiestaUI change.

Final rotation, ordered so a text-heavy board never follows another one:

| # | Title | Device | Kind |
|---|-------|--------|------|
| 1 | Morning Dashboard | Flagship 22×6 | text |
| 2 | Market Movers | Flagship 22×6 | **new** — data + color |
| 3 | Sunset Gradient | Flagship 22×6 | art |
| 4 | Weekly Forecast | Flagship 22×6 | **new** — data + color |
| 5 | Daily Briefing | Note 15×3 | text |
| 6 | Game Day | Note 15×3 | **new** — data + color |
| 7 | Transit + Markets | Note Array 2×1 | text |
| 8 | Sunrise Column | Note Array 1×2 | art |
| 9 | Rainbow Wash | Note Array 2×2 | art |

Board content (`{tile}` counts as one cell; all glyphs used — `+ - % , . :` —
are in `BOARD_CHARS`):

**Market Movers** (Flagship, 22 cols). Green and red tiles gutter the board so
direction reads before the numbers do; price and change columns align across
rows.

```
MARKET MOVERS
{green}AAPL  232.10  +1.24%
{green}NVDA  121.44  +0.86%
{red}TSLA  244.90  -2.10%
{red}BTC   61,204  -1.40%
{green}S+P   5,712   +0.42%
```

**Weekly Forecast** (Flagship, 22 cols). One condition tile per day — yellow
sun, blue rain, violet fog, orange heat.

```
SF FORECAST
MON {yellow} SUNNY     68 54
TUE {blue} RAIN      61 52
WED {violet} FOG       59 51
THU {yellow} SUNNY     70 55
FRI {orange} HOT       78 58
```

**Game Day** (Note, 15 cols). Team-color tiles against the score.

```
{orange}SF 24  {red}LA 17
4TH QTR   2:41
{orange}SF BALL 1ST+10
```

### 3. Random colorful opener

Nine boards at 4.8s each is a 43-second loop — longer than most visitors stay,
so the rotation starts at a random index instead of always at board 1. The
start is drawn only from boards flagged `opener: true`: **Market Movers** and
**Weekly Forecast**. Both are Flagship-sized and show data and color at once,
which is the strongest first impression. Game Day is colorful but renders on
the small 15×3 Note grid, so it is not an opener. From there the rotation
proceeds in table order and wraps.

Randomizing is safe because `HeroBoard` renders inside `<BrowserOnly>` — there
is no server-rendered markup to mismatch.

### 4. Scramble handles mixed cells

`runScramble` currently branches on a per-board `kind: "text" | "art"` field:
art rows are split with `row.match(/\{[^}]+\}/g)`, text rows with
`Array.from(row)`. A mixed board breaks both paths — as text, `{red}` shreds
into six cells that flap through garbage glyphs and briefly render as literal
`{`, `r`, `e` characters.

Replace both with one tokenizer that walks a row emitting `{...}` as a single
cell and every other character as its own cell. Each cell then scrambles
through values of its own type: color cells flap through colors, character
cells flap through glyphs. Mixed boards need no special case, and the `kind`
field disappears from `BoardConfig` entirely.

The staggered settle timing (`4 + col * 0.8 + row * 1.6 + rand(0..7)` frames)
is unchanged.

## Testing

`docs-site` has no test runner. Verification is:

- `npm run typecheck`, `npm run lint`, `npm run format:check`
- `npm run build` — the production Docusaurus build
- Screenshots of all nine boards from a local dev server, confirming each
  caption, that no row overflows its grid, and that the mixed boards scramble
  through colors rather than glyph garbage
- Reduced-motion path: message set directly, caption still correct

Per the repo's container rules, all of this runs in a throwaway node container
rather than installing `docs-site` dependencies on the host.

## Out of scope

- Plugin cards further down the homepage — they already carry names and
  descriptions
- `BoardScreenshot` in the plugin docs pages — static images with alt text
- Any FiestaUI change
