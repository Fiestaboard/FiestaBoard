# Section header + breadcrumb navigation — design

Date: 2026-10-05 · Target branch: `next` · Repos: FiestaBoard (web), FiestaUI

## Problem

Every route renders its own `PageLayout › PageCard › PageHeader`. Drilling from a
list to one of its items (`/displays` → `/displays/:boardId`) unmounts the whole
card and mounts a new one, so the header fades in again (`animate-card-fade-in`),
its hooks re-run, and the page visibly "reloads". Each detail route then invents
its own way back: a ghost "Back to displays" button, a "Back to marketplace"
button above a hand-rolled hero card, or (Pages) a full-screen slide-up editor.

## Goal

FiestaBoard is hub-and-spoke: a section (the hub) and the things inside it (the
spokes). Navigating within a section keeps the section's header mounted and
still. Drilling in drops a breadcrumb and a lower-level sub-header beneath it,
animated as an expand; going back collapses them.

Success:

- Moving between a section's list and its detail never remounts the `PageCard`
  or `PageHeader` (verifiable: header DOM node identity survives navigation).
- Every drill-in shows `Section › Item` with the section crumb as the way back;
  the bespoke Back buttons are gone.
- Expand/collapse animates, and snaps under `prefers-reduced-motion`.
- Deep links and refresh on a detail URL still land on the drilled-in state.

## Scope

All four drill-in flows:

| Section | List (index child) | Detail child | Crumb label |
|---|---|---|---|
| Displays | `/displays` | `/displays/:boardId` | board name |
| Integrations | `/integrations` (tabs via `?tab=`) | `/integrations/:pluginId` | plugin name |
| Pages | `/pages` | `/pages/new`, `/pages/edit/:id` | page name / "New page" |

`/pages/edit` (index, no id) keeps its current redirect-to-`/pages` behaviour,
now as a child of the Pages layout.

Also in this branch: sidebar primary order becomes **Home, Displays, Pages,
Collections, Schedule, Integrations** (`web/src/components/navigation-sidebar.tsx`).

Out of scope: Collections, Schedule, Settings, Home (no drill-in routes today).

## Approach — section layout routes (chosen)

Rejected: View Transitions morph (header still remounts; only hides the
symptom; uneven browser support) and in-page panels (loses URLs).

### Routing (FiestaBoard `web/app/routes.ts`)

Each section becomes a layout route whose module renders the shell and an
`<Outlet>`:

```ts
layout("routes/displays.tsx", [
  route("displays", "routes/displays._index.tsx"),
  route("displays/:boardId", "routes/displays.$boardId.tsx"),
]),
```

(or `route("displays", "routes/displays.tsx", [index(...), route(":boardId", ...)])`
— whichever keeps existing route files and tests least disturbed.)

The layout module owns: `PageLayout`, `PageCard`, the section `PageHeader`
(icon, hue, title, description, list-level action), and a `SectionDetail`
context provider.

### Detail registration

Detail names are dynamic (a board rename, a plugin manifest name), so they
can't live in a static route `handle`. A child registers itself:

```ts
useSectionDetail({
  label: board.name,          // crumb + sub-header title
  description: outputName,    // sub-header description (optional)
  actions: <...>,             // sub-header action slot (optional)
  backHref: "/integrations?tab=marketplace", // crumb href; defaults to the section root
});
```

The layout reads the registered detail. No registration (the index child) means
"at the hub": breadcrumb and sub-header collapsed, header description expanded,
list-level action visible. Registration clears on unmount.

Integrations' crumb returns to the tab the user came from: `backHref` is taken
from the referring `?tab=` (passed through link state), defaulting to
`/integrations`.

### FiestaUI pieces

Added to `@fiestaboard/ui` (released first; FiestaBoard pins an exact version):

1. **`PageHeader` gains `collapsed?: boolean`.** Collapses the description row
   (and the `children` action slot) with the grid-rows technique below. The
   `h1` with icon and title never moves.
2. **`PageSubheader`** — a block inside `PageCard`, after `PageHeader`:
   - a `Breadcrumb` row (existing component) — `Section › Item`, the section
     crumb a link, the item `aria-current="page"`;
   - an `h2` title at a level below `page-title`, optional description,
     right-aligned action slot;
   - `open: boolean` drives the expand/collapse.
   - Its `data-slot` gets block padding and a top rule from `PageCard`, the same
     way `page-header` / `page-toolbar` do.
3. **Animation primitive** — `grid-template-rows: 0fr → 1fr` with an inner
   `min-h-0 overflow-hidden`, plus opacity, ~200ms ease-out. Content height is
   never measured in JS. `motion-reduce:transition-none`. Collapsed content is
   `inert` so it leaves the tab order and the accessibility tree.

The breadcrumb accepts `asChild` links, so FiestaBoard passes its `smart-link`.

### Route-by-route changes

- **Displays:** `displays.$boardId.tsx` drops its own `PageLayout/PageCard/
  PageHeader` and Back button; registers `{label: board.name, description:
  outputName}`; renders its `PageSection`s as before. `displays._index.tsx`
  drops its shell; "Add display" stays the layout's list-level action.
- **Integrations:** the detail's hero card and Back button become the
  sub-header (title = plugin name; description = author/category badge;
  actions = its existing install/enable controls). `BoardShowcase`, README and
  config render below as `PageSection`s. The index keeps its tabs/toolbar under
  the header.
- **Pages:** `pages.new` / `pages.edit.$id` render the editor inside the Pages
  card, under `Pages › <page name>` ("New page" until named). The
  `slide-up`/`slide-down` view-transition types on these routes are
  removed — the expand replaces them. The editor's own close button navigates
  to `/pages` (same as the crumb); its full-height `flex-1 min-h-0` sizing is
  preserved by giving the Pages layout `PageLayout fillHeight` /
  `PageCard fillHeight` while drilled in. The AI page-editor bridge
  (`PageEditorShell`) is unchanged.

### Accessibility

- Heading outline: `h1` section, `h2` item, `h3`/CardTitle for sections below.
- On drill-in, focus moves to the `h2` (tabIndex -1) so screen-reader users hear
  where they landed; on return, focus goes to the list's previously opened item
  when it still exists, else the `h1`.
- Breadcrumb is a named `<nav>` (localized `aria-label`).
- No left accent rails anywhere (house rule).

### i18n

New keys: breadcrumb nav label, "New page". Removed: `displays.back`,
`integrations.backToMarketplace` (and any equivalents) from every locale file.

## Testing

- Vitest: `useSectionDetail` register/clear; layout renders collapsed vs
  expanded; crumb href and `aria-current`; reduced-motion class present.
- FiestaUI: unit tests + stories for `PageSubheader` and `PageHeader collapsed`
  (open/closed, long titles wrapping at 390px, dark mode).
- Playwright: list → detail → crumb back on each section asserting the header
  element is the same node (tag it via `evaluate` before navigating) and no
  `animate-card-fade-in` restart; deep-link refresh on a detail URL; sidebar
  order.
- Fable design review after each step, with screenshots in light/dark at
  desktop and 390px.

## Sequencing

1. FiestaUI: `PageHeader collapsed`, `PageSubheader`, stories, tests → PR →
   release.
2. FiestaBoard on `feat/section-breadcrumb-nav` (from `next`): bump
   `@fiestaboard/ui`; section layout + `useSectionDetail`; Displays; sidebar
   order.
3. Integrations.
4. Pages.
5. PR into `next`.

Until the FiestaUI release lands, FiestaBoard work can run against a local
`npm link`/file build of FiestaUI so steps 1 and 2 overlap.
