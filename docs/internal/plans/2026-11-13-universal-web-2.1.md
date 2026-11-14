# Slice 2.1: information architecture and nav (WEB-01, WEB-02, WEB-14)

**Branch:** `feat/universal-web-2.1-ia-nav`, base `feat/universal-web-2.0-fiestaui-alpha` (#2471).
**Figma** (`ZQ8RMELCO6qEOFZUnQu36e`): 07 `53:100587` (bottom nav), `57:63379` (390 Home), `61:17544` (900 rail); 07a `308:36070` (More sheet), `308:36108` (FiestaBot on the phone); 07e §1 `318:46000`, `333:52957`, `333:54525`, `320:6520`, `320:7936`, `320:8881` (Settings).

## Goal

One IA for every width:

```text
Home · Pages (▸ Collections) · Schedule · Displays │ Integrations · Staff Picks · Settings · Help & Docs
```

- Below 768px a bottom tab bar (Home · Pages · Schedule · Displays · More). More holds the rest, FiestaBot, the Settings › Hub group and the hub line.
- From 768px the rail (`railBreakpoint="md"`).
- The Integrations row carries the NavItem badge when an integration needs setting up (07a "one badge, one story"); on a phone it rolls up onto More.
- Settings becomes a list-detail: a hub card, the You group, and the Hub group (Network · AI provider · System & backups · Language & time), each section at `/settings/:section`.

## Design

- `web/src/lib/nav-items.ts`: the IA as data. `navItemsFor("rail" | "bottom-nav")` (the tab bar drops nested Collections), `isNavItemActive` (on the tab bar Pages lights for `/collections`), `integrationsNeedingAttention`, `HUB_SETTINGS_LINKS`.
- `web/src/hooks/use-below-rail.ts`: `RAIL_BREAKPOINT = "md"` and a `matchMedia` hook. The Sidebar is one component for both chromes, but the two list different things, so the app picks the list by width.
- `NavigationSidebar`: `variant="bottom-nav"`, `railBreakpoint="md"`, `labels.more`, the badge, and `renderSettingsMenu` returning `MoreSheetExtras` on mobile and the account menu on the rail. The gear no longer lights: the Settings row does (07e).
- `MoreSheetExtras` (`more-sheet.tsx`): FiestaBot row, divider, Hub group heading and rows (NavList at 48px), hub line. Rendered into the Sidebar's More drawer.
- `MainContent` and every `PageLayout`: `railBreakpoint="md"`; MainContent `bottomNav`.
- FiestaBot drawer and dock: clear the bar with `--bottom-nav-offset`; the drawer's phone/rail switch moves to `md`.
- Settings: `route("settings/:section?")`. Legacy `?section=` links redirect to the matching path and keep the other query parameters (the OAuth return). AI choreography targets the new paths.

## The More sheet (Jev `jev_decide`, p=0.82: `interim_drawer`)

The 07a More sheet is a floating bottom sheet (grabber, "More" title, chevron rows, inset card above the bar). FiestaUI cannot draw it yet: Sidebar `bottom-nav` opens its built-in drawer and has no hook to open an app sheet, and the 1.3 Sheet has no floating variant. Options weighed: the interim drawer filled with the 07a content (chosen); a synthetic fifth item whose `renderLink` returns a button that opens a web Sheet (hacky, and the More roll-up would be the app's); waiting on a FiestaUI PR. Recorded as a FiestaUI gap.

## Tests (written first)

- vitest: `nav-items.test.ts` (new), `navigation-sidebar.test.tsx` (bottom nav, More contents, Hub group, badge, rail breakpoint), `settings-hub-group.test.tsx` (replaces `settings-tabs.test.tsx`: index, detail, phone list/detail, legacy links), `settings-hardware-redirect.test.tsx`, choreography tests (new paths). New files join the coverage list.
- Playwright: `tests/nav-ia.spec.ts` at 390 / 900 / 1280, with axe on More and Settings. Existing specs that drove the settings tabs or the hamburger are updated.
- Typecheck, lint, format, build in `node:24`.

## Review completion (Codex handoff, 2026-11-13)

- Preserve the inherited review work, use FiestaUI #404 `ListRow selected`, and merge the updated 2.0 base when pushed.
- Keep the container-query Settings layout (Jev `container` 0.64), gated to rail widths so a 700px phone still uses the full width.
- Initialize tablet collapse in SidebarProvider, retain the session-only toggle and restore the stored desktop preference when leaving the band.
- Preserve hash-to-section redirects and provide stable DOM targets for scroll/pulse, including cards that load asynchronously.
- Keep About in System & backups and document the load-bearing OAuth shim. Hub-line changes remain owned by 2.3.
- Verify unit coverage, browser flows one spec/worker at a time, axe, screenshots, typecheck, lint, format and build. Keep #2480 draft until an npm alpha includes #404.
