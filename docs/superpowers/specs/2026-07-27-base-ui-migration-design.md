# Base UI Migration Design

**Date:** 2026-07-27
**Goal:** Remove all Radix UI / shadcn-era Radix dependencies from the web UI and rebuild the
primitive layer on [Base UI](https://base-ui.com) (`@base-ui/react`), with zero intended
behavior or visual change for the rest of the app.

## Why

- Base UI is the successor library built by the Radix + Floating UI + Material UI teams and is
  where active development happens (Radix primitives are in maintenance mode).
- Consolidates two Radix dependency styles currently in the tree (`@radix-ui/react-*` scoped
  packages **and** the `radix-ui` umbrella package) into a single dependency.
- Base UI's `render` prop, CSS-first animation model (`data-open` / `data-closed` /
  `data-starting-style` / `data-ending-style`), and CSS variables (`--anchor-width`,
  `--available-height`) replace Radix's `asChild` / `data-state` / `--radix-*` equivalents.

## Scope

All Radix usage is contained in `web/src/components/ui/` (13 files) plus two Tailwind
`data-[state=...]` selectors in app code. App-level components import only the shadcn-style
wrappers, so the migration is an adapter-layer rewrite.

### Approach (chosen): adapter wrappers preserve the existing API

The wrappers in `web/src/components/ui/` keep their **exported names, props, and semantics**
(including `asChild`, `side`/`align`/`sideOffset` on `*Content` components, string-valued
Radix-style props). Internally they re-implement on Base UI parts. App code (54 `asChild`
usages across 24 files, 16 Select consumers, 20 Tooltip consumers, ...) stays untouched except
for two files styling against `data-[state=...]`.

Rejected alternative: migrating every call site to idiomatic Base UI (`render` props,
`items` on Select roots). Far more churn and review surface for no functional gain; can be
done incrementally later behind the stable wrapper API.

## Component mapping

| Wrapper | Radix source | Base UI part(s) | Notes |
| --- | --- | --- | --- |
| `dialog.tsx` | `@radix-ui/react-dialog` | `Dialog.Root/Trigger/Portal/Backdrop/Popup/Title/Description/Close` | `Overlay` → `Backdrop`, `Content` → `Popup`; animation classes move to `data-[open]` / `data-[ending-style]` |
| `alert-dialog.tsx` | `@radix-ui/react-alert-dialog` | `AlertDialog.*` | `Action`/`Cancel` are styled `AlertDialog.Close` wrappers keeping their `data-testid`s |
| `sheet.tsx` | `@radix-ui/react-dialog` | `Dialog.*` | keeps inline keyframe animations |
| `select.tsx` | `@radix-ui/react-select` | `Select.Root/Trigger/Value/Icon/Portal/Positioner/Popup/List/Item/ItemIndicator/ItemText/Group/GroupLabel/Separator/ScrollUp(Down)Arrow` | The `Select` wrapper walks its children to build the Base UI `items` map (value → rendered item content) so the trigger shows the selected item's content like Radix did; `SelectValue` keeps `placeholder`; `alignItemWithTrigger` disabled to preserve popper-style positioning; `--radix-select-trigger-width` → `--anchor-width` |
| `dropdown-menu.tsx` | `radix-ui` (Menu) | `Menu.Root/Trigger/Portal/Positioner/Popup/Item/Group/GroupLabel/Separator/CheckboxItem/RadioGroup/RadioItem/SubmenuRoot/SubmenuTrigger` | `data-[state=open]` → `data-[popup-open]`; `data-[highlighted]` styling added alongside `focus:` |
| `tooltip.tsx` | `@radix-ui/react-tooltip` | `Tooltip.Provider/Root/Trigger/Portal/Positioner/Popup` | `delayDuration` → `delay` translated in wrapper |
| `tabs.tsx` | `@radix-ui/react-tabs` | `Tabs.Root/List/Tab/Panel` | `data-[state=active]` → Base UI selected-tab attribute |
| `accordion.tsx` | `@radix-ui/react-accordion` | `Accordion.Root/Item/Header/Trigger/Panel` | Radix `type="single" collapsible` + string value adapted to Base UI array `value`/`openMultiple`; grid-rows keyframes retargeted |
| `collapsible.tsx` | `@radix-ui/react-collapsible` | `Collapsible.Root/Trigger/Panel` | `group-data-[state=open]` app selector → `group-data-[panel-open]` |
| `switch.tsx` | `@radix-ui/react-switch` | `Switch.Root/Thumb` | `data-[state=checked]` → `data-[checked]` / `data-[unchecked]` |
| `slider.tsx` | `radix-ui` (Slider) | `Slider.Root/Control/Track/Indicator/Thumb` | array value API preserved |
| `scroll-area.tsx` | `@radix-ui/react-scroll-area` | `ScrollArea.Root/Viewport/Scrollbar/Thumb/Corner` | |
| `button.tsx`, `badge.tsx` | `@radix-ui/react-slot` | `useRender` | `asChild` implemented via Base UI's `useRender` |

`checkbox.tsx`, `label.tsx`, `input.tsx`, etc. are plain HTML and unchanged. `sonner`
(toasts), `cva`, `tailwind-merge` are unrelated and stay.

### `asChild` compatibility shim

Base UI composes via `render={<Child/>}` instead of `asChild`. Wrappers whose Radix
counterparts supported `asChild` accept an `asChild?: boolean` prop; when set, the single
child element is passed as `render` and children are omitted. This keeps all 54 app call
sites source-compatible.

## Dependencies

Remove: `@radix-ui/react-accordion`, `-alert-dialog`, `-dialog`, `-scroll-area`, `-select`,
`-slot`, `-switch`, `-tabs`, `-tooltip`, `radix-ui`.
Add: `@base-ui/react@^1.6.0`.
Lockfile regenerated inside the Docker web container (`--legacy-peer-deps` per repo policy).

## Risks and mitigations

- **Select trigger label rendering** — Radix portals the selected item's content into the
  trigger; Base UI needs an `items` map. The wrapper derives it from children traversal.
  Mitigated by the existing select-heavy unit tests and e2e specs.
- **jsdom unit tests** — `src/__tests__/setup.ts` shims (`scrollIntoView`, pointer capture,
  `ResizeObserver`) were added for Radix; Base UI may need additions. Fixed as surfaced by
  vitest.
- **Open/close animations** — Base UI keeps popups mounted while `data-ending-style` is
  present; exit-animation classes are re-keyed accordingly. Verified visually via recorded
  videos.
- **Callback arity** — Base UI change callbacks pass `(value, eventDetails)`; existing app
  handlers typed `(value) => void` remain compatible.
- **`tsc --noEmit`** has ~120 pre-existing errors on main; CI gates eslint + prettier +
  vitest only. Success criterion is "no new type errors attributable to this change".

## Validation plan

1. Full vitest suite, eslint, and `prettier --check` in the Docker web container.
2. Docker image built from the branch, run on `:4499` against the mock board with auth
   disabled; the **entire** Playwright e2e suite (`web/tests`) run with
   `BASE_URL=http://localhost:4499`.
3. Screen-recorded Playwright walkthrough (video on) exercising dialog, alert dialog, sheet,
   select, dropdown menu, tabs, switch, tooltip, accordion/collapsible flows as proof.
