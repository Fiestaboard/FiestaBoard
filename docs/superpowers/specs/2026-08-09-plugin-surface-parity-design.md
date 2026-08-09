# Plugin surface parity: app marketplace ↔ docs plugin directory

**Date:** 2026-08-09
**Status:** Approved (design)

## Problem

`fiestaboard.app/plugins` and the in-app Integrations → Marketplace show the same
plugins with almost nothing in common.

| | Docs `/plugins` | App Marketplace |
|---|---|---|
| Card | Title + colored category badge, description, "by author", **scaled board teaser strip** | Lucide icon tile + name + Install button, description, plain grey badge |
| Detail | **Live board hero** (device-shape tabs + Black/White toggle), header, README | Header card + README |
| Board content | Everywhere | **Nowhere** |

The gap that matters is the last row: the docs site sells a plugin by showing
what it puts on your board; the app never shows the board at all. A user who
browsed the directory and then opened the app does not recognise the same
product.

A second problem sits underneath: the docs implementation is CSS modules local
to `docs-site/`. Any convergence done by copying it will drift again — and
docs-site is expected to move to its own repository, at which point copied code
becomes unmaintainable across repos.

## Goals

1. Put the actual board on both the app's plugin cards and its plugin detail page.
2. Make the two surfaces share one implementation, owned by `@fiestaboard/ui`.
3. Keep the app's own affordances (Install, Add Instance, instance management).
4. Leave a seam that survives docs-site moving to its own repo: the only thing
   the two repos share is a published npm package.

## Non-goals

- Migrating docs-site onto the shared components. That needs a vendored-tarball
  bump (`1.5.0` → new release) and is its own risk surface — follow-up PR.
- Unifying the app's local `web/src/components/static-board-display.tsx` with
  FiestaUI's `StaticBoardDisplay`. Pre-existing duplication, unrelated.
- Translating the module-level English `CATEGORY_LABELS` map in
  `integrations._index.tsx`. Pre-existing; only strings this change writes are
  localized.
- The installed-plugins tab (a table, not cards) is unchanged.

## Architecture

Three layers, bottom-up.

### Layer 1 — FiestaUI: new `plugin/` component group

Presentational only, matching the existing FiestaUI contract: no router, no
i18n framework, no data fetching. Labels are injected as props (the
`LanguageSelector` pattern).

**`src/lib/board-previews.ts`**

```ts
export interface BoardPreviewEntry {
  label?: string;
  device_type?: "flagship" | "note" | "note_array";
  notes_wide?: number;
  notes_tall?: number;
  rows: string[];
}
export interface PreviewShapeLabels { flagship: string; note: string; noteArray: string }
export function previewLabel(p: BoardPreviewEntry, labels?: PreviewShapeLabels): string;
export function previewMessage(p: BoardPreviewEntry): string;
```

Lifted verbatim in behaviour from `docs-site/src/plugin-data.ts` so tab labels
can't diverge; `noteArray` is a format string containing `{w}` and `{h}`.

**`components/plugin/plugin-category-badge.tsx`**

`PluginCategoryBadge({ category, label, className })` — the docs palette
(weather/transit/data/entertainment/art/utility/home), light and dark, defined
once. Unknown categories fall back to the neutral `secondary` badge.

**`components/plugin/scaled-board-teaser.tsx`**

`ScaledBoardTeaser({ teaser, boardType, tiles?, minScale?, maxScale?, className })`
— the `ResizeObserver` measure-and-transform wrapper currently inlined in
`docs-site/src/pages/plugins/index.tsx` as `ScaledTeaser`. Viewport breakpoints
can't see card width, so it measures.

**`components/plugin/plugin-card.tsx`**

```ts
interface PluginCardProps {
  name: string;
  description?: string;
  /** Pre-formatted by the consumer, e.g. "by FiestaBoard Team" — the
   *  by-{author} wording is a localized string, not the component's business. */
  authorLabel?: ReactNode;
  category?: string;
  categoryLabel?: string;
  teaser?: string;
  boardType?: "black" | "white";
  /** Renders the card's primary link. Receives a className that makes it a
   *  stretched link covering the whole card. */
  renderLink: (props: { className: string; children: ReactNode }) => ReactNode;
  /** Trailing action slot (Install button, Installed badge). Rendered above
   *  the stretched link so it is not a nested interactive element. */
  action?: ReactNode;
  className?: string;
  style?: CSSProperties;
}
```

Anatomy (the docs card, plus the action slot):

```
┌──────────────────────────────┐
│ Air Quality & Fog  [WEATHER] │   title + colored category badge
│ Display air quality (AQI),   │   description, clamped
│ fog/visibility conditions…   │
│ by FiestaBoard Team [Install]│   author line + action slot
│ ──────────────────────────── │
│  ▐A▌▐Q▌▐I▌▐ ▌▐4▌▐5▌▐ ▌▐C▌    │   scaled teaser footer
└──────────────────────────────┘
```

`renderLink` is a render prop because the two consumers use different routers
(Docusaurus `Link`, the app's `smart-link`) — this is the seam that survives
the repo split. The stretched-link pattern (`after:absolute after:inset-0`)
also removes the nested-interactive a11y violation the app card has today
(a `<Button>` inside an `<a>` with `preventDefault`).

**`components/plugin/board-showcase.tsx`**

```ts
interface BoardShowcaseProps {
  previews: BoardPreviewEntry[];
  previewLabel?: string;                       // accessible board label
  size?: "sm" | "md" | "lg";
  boardType?: "black" | "white";                // optional controlled
  defaultBoardType?: "black" | "white";
  onBoardTypeChange?: (t: "black" | "white") => void;
  labels?: Partial<ShowcaseLabels>;             // English defaults
  className?: string;
}
```

Device-shape switching uses the existing FiestaUI `Tabs` primitive (Base UI) so
roving tabindex, arrow keys, and `tablist`/`tab`/`tabpanel` wiring are correct —
the docs implementation hand-rolls `role="tab"` with no `tabpanel`, which this
fixes. The board-color control is two `aria-pressed` toggle buttons in a
segmented pill. Repeated shape labels are numbered ("Flagship", "Flagship 2")
so every tab has a distinct accessible name, as docs does today.

Each component ships a story, is covered by `test-storybook` (a11y), and gets
VRT baselines. Released as a FiestaUI minor.

### Layer 2 — FiestaBoard API: teaser/previews on registry entries

Installed plugins already expose `teaser` and `previews` through
`PluginManifest.to_dict()`. Registry entries — which is what the marketplace
lists, mostly *not installed* — expose neither, and the seed file
`plugin-previews.json` is not even in the image.

- `Dockerfile`: `COPY plugin-previews.json ./plugin-previews.json`.
- `src/plugins/previews.py`: `load_preview_seed(path=None) -> dict[str, dict]`,
  reading the root `plugin-previews.json` (`{"plugins": {id: {teaser, previews}}}`),
  cached, returning `{}` on a missing or unparseable file — a missing seed
  degrades to "no board on the card", never an error.
- `PluginRegistry.get_registry_entries()` merges per entry:
  **installed manifest wins → seed is the fallback → empty**. Manifest-first
  matches the documented contract in `PLUGIN_DEVELOPMENT.md` and means an
  installed plugin shows its own current preview rather than a stale seed.
- `web/src/lib/api.ts`: `RegistryEntry` gains `teaser?: string` and
  `previews?: BoardPreviewEntry[]`.

Payload cost: ~50 plugins × a 6-row preview ≈ tens of KB on an endpoint that is
already cached for 5 minutes client-side. Acceptable; no new round trips, no
network dependency, works offline.

### Layer 3 — Web app

**Marketplace card** (`RegistryPluginCard` in `integrations._index.tsx`)
rebuilt on `PluginCard`: docs anatomy, colored `PluginCategoryBadge`, teaser
footer from `entry.teaser`, Install button / Installed badge in the `action`
slot. A plugin with no teaser renders the card without the footer strip
(no empty band).

Board color is the user's *actual* board colour —
`currentBoard?.board_color ?? getEffectiveBoardColor(boardSettings)`, the same
expression `active-page-display.tsx` uses — not the UI theme. The docs site has
to guess from `colorMode`; the app knows, so the teaser shows the plugin on the
board the user owns. The detail page seeds the showcase from the same value and
the Black/White toggle overrides it from there.

**Detail page** (`integrations.$pluginId.tsx`) becomes board-first:

```
[← Back to Marketplace]
┌────────────────────────────────────┐
│  [ Flagship ] [ Note ]             │
│   ▛▀▀▀ live board preview ▀▀▀▜     │
│      ( Black Board | White Board ) │
└────────────────────────────────────┘
┌─ card ─────────────────────────────┐
│ [◧] Air Quality & Fog  [Weather]   │
│ by FiestaBoard Team · needs ≥2.10  │
│                 [GitHub] [Install] │
│ ────────────────────────────────── │
│ Display air quality (AQI), fog…    │
└────────────────────────────────────┘
┌─ Documentation ────────────────────┐
```

The showcase renders only when the entry has previews; otherwise the page keeps
today's header-first layout exactly. No new fetch — the detail page already
loads `/plugins/registry`, which now carries the previews.

**i18n.** New keys in all 14 locale files under `pluginDetail` and
`integrations`: board shape labels, board color labels, control group labels,
board preview accessible label, plus `install` / `installedBadge` for the card
(today hardcoded English inside `RegistryPluginCard`).

## Data flow

```
plugins/<id>/manifest.json ──┐
                             ├─► get_registry_entries()  ──► GET /plugins/registry
plugin-previews.json (seed) ─┘        manifest wins              │
                                                                 ▼
                                                RegistryEntry{teaser, previews}
                                                       │              │
                                            PluginCard ▼              ▼ BoardShowcase
                                        (marketplace grid)      (detail page hero)
```

## Error handling

- Missing/corrupt `plugin-previews.json` → `load_preview_seed()` logs and
  returns `{}`; entries carry `teaser: ""`, `previews: []`; UI omits the strip
  and the hero. Never fatal.
- A malformed `teaser` (over-wide, bad color token) is truncated/padded by
  `BoardTeaser` — it already renders exactly `tiles` tiles.
- A preview with an unknown `device_type` falls through
  `resolveDimensions()`'s flagship default, as it does on the docs site today.
- Plugins installed from git and absent from the registry are unchanged: the
  detail route already only resolves registry entries.

## Testing

- **FiestaUI:** a story per component; `test-storybook` a11y run; VRT baselines
  for card, badge, teaser, showcase (both board colors, both themes).
- **Python:** `load_preview_seed()` — happy path, missing file, bad JSON;
  `get_registry_entries()` — manifest-wins, seed-fallback, neither.
- **Web (vitest):** marketplace card renders the teaser and the install action
  and links to the detail route; card without a teaser renders no strip; detail
  page renders the showcase when previews exist and the plain header when they
  don't.
- **i18n:** key parity across all 14 locales (the existing audit rule).

## Rollout

1. FiestaUI PR → minor release (`1.7.0`).
2. FiestaBoard PR: API merge + `RegistryEntry` type + card + detail page + i18n,
   with `@fiestaboard/ui` bumped to the new version. ← *this change*
3. Follow-up PR: docs-site vendored tarball bump and migration onto
   `PluginCard` / `PluginCategoryBadge` / `ScaledBoardTeaser` / `BoardShowcase`,
   deleting the equivalent CSS-module code.
