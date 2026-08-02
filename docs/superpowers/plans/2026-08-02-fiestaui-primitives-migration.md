# FiestaUI Primitives Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace essentially all raw HTML in `web/app/**` and `web/src/**` with `@fiestaboard/ui` components, then make it permanent with an ESLint rule.

**Architecture:** Six independent wave PRs into `main`, each applying the same mechanical recipe to a fixed file list, verified by the existing CI suites plus before/after screenshots. The final wave flips on `react/forbid-elements`. Spec: `docs/superpowers/specs/2026-08-02-fiestaui-primitives-adoption-design.md`.

**Tech Stack:** React 19, React Router v7, `@fiestaboard/ui` (needs the minor release from the companion FiestaUI plan `docs/superpowers/plans/2026-08-02-primitives-for-zero-raw-html.md` in the FiestaUI repo), ESLint 9 flat config with `eslint-plugin-react`.

## Global Constraints

- **Prerequisite:** `web/package.json` must be on the `@fiestaboard/ui` minor that ships `Text`/`Heading`/`Code`/`TextLink`/`List`/`Table`/`Box` (delivered by the evergreen upgrade PR #1471 pipeline). Waves 1–6 cannot start before it lands on `main`.
- Never run `npm install`/`npm run dev` on the host (CLAUDE.md). All checks run in Docker: `docker compose -f docker-compose.dev.yml run --rm --profile test web sh -c "npm ci && npm run typecheck && npm run lint && npm run format:check && npm test"`.
- Each wave: its own feature branch off fresh `main` (`feat-primitives-wave-N`), own PR, straight to `main`. Use an isolated worktree (concurrent sessions share the main checkout).
- Prettier runs in CI (`lint-web` fails on `prettier --check`) — run `npm run format` in the container before pushing.
- Normalization is bounded to the blessed variant scales (table below). Anything that cannot snap cleanly: keep the exact classes via `className` on the primitive, and log the pattern as a comment on the epic issue — recurring patterns get promoted to FiestaUI variants instead of repeated one-offs.
- Visual evidence per wave: run the branch's prod image on `:4499` (`docker build -t fiestaboard-wave-test . && docker run --rm -d -p 4499:3000 --name fiestaboard-wave-test fiestaboard-wave-test`), screenshot each affected screen before/after, attach to the PR.
- Do not migrate: `**/__tests__/**`, `*.stories.tsx`, anything under `web/tests/`.

## The Migration Recipe (applies to every wave)

Work file-by-file. For each raw element, pick the first matching row:

| Raw pattern | Replacement (`@fiestaboard/ui`) |
|---|---|
| `<div className="flex items-center justify-between gap-4">` | `<Flex align="center" justify="between" gap="4">` |
| `<div className="flex flex-col gap-2">` or `<div className="space-y-2">` | `<Stack gap="2">` |
| `<div className="grid grid-cols-2 gap-4">` | `<Grid cols="2" gap="4">` |
| `<div className="flex ...">` with extra classes (borders, padding, colors) | `Flex`/`Stack` variant props for layout + keep the rest in `className` |
| any other `div` (positioned overlays, portal/canvas hosts, plain wrappers) | `<Box className="...">` (or `<Box as="section">` etc. for semantic elements) |
| `<p className="text-sm text-muted-foreground">` | `<Text tone="muted">` |
| `<p>` / `<p className="text-sm">` | `<Text>` (Text defaults to `size="sm"`) |
| `<span className="text-xs ...">` | `<Text as="span" size="xs">` |
| `<h2>`/`<h3>`/`<h4>` with title styling | `<Heading level={3} size="...">` (level = same element as before; `h1` stays `PageHeader`) |
| `<code className="...">` (inline) | `<Code>` |
| `<a href ...>` (plain anchor) | `<TextLink href ...>` — react-router `<Link>`/`<NavLink>` stay as they are |
| `<ul className="space-y-1">` + `<li>` | `<List gap="1">` + `<ListItem>` |
| `<ol className="list-decimal ...">` | `<List as="ol" marker="decimal">` |
| `<table>`/`<thead>`/`<tbody>`/`<tr>`/`<th>`/`<td>` | `Table`/`TableHeader`/`TableBody`/`TableRow`/`TableHead`/`TableCell` (drop any hand-rolled `overflow-x-auto` wrapper div — `Table` brings its own) |
| `<form>` | `<Box as="form">` |
| `<section>`/`<main>`/`<header>`/`<footer>`/`<nav>` | `<Box as="section">` etc. (unless a chrome component like `MainContent` already covers it) |
| `<strong>` | `<Text as="span" weight="semibold">` |
| `svg`, `canvas`, `iframe`, `img`, `br`, `em`, `small`, `kbd`, `pre`, `figure`, `dl`, `dt`, `dd` | **leave raw** (allowlisted) |

**⚠️ Inline-span sharp edge (from FiestaUI's final review):** a raw `<span>` inherits size/color/weight from its context; `<Text as="span">` resets all three to its defaults (`text-sm text-foreground font-normal`). Do NOT mechanically swap spans inside colored/sized contexts (badges, alerts, buttons, headings) — either pass matching `size`/`tone`/`weight` props, or if the span exists purely for semantics/hooks with fully inherited styling, leave it raw only if allowlisted; otherwise carry the context explicitly. Same for bare `<ul>` → `List`: `gap` defaults to `"1"`, so pass `gap="0"` when the original had no spacing.

**Normalization snapping (intentional visual diffs, reviewed via screenshots):**

- Gap/spacing snaps to the enumerated scale `0, 0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 12`: `gap-7`→`gap="6"`, `space-y-10`→`gap="8"` (nearest step; ties round down).
- Arbitrary font sizes snap to `xs/sm/base/lg`: `text-[13px]`→`size="sm"`, `text-[11px]`→`size="xs"`.
- Muted/status text colors snap to `tone` values instead of hand-picked grays.
- Title-ish font styling on headings snaps to `Heading`'s built-in recipe (`font-semibold leading-none tracking-tight`).

**Worked example** (real code, `src/components/settings/about-card.tsx`):

Before:

```tsx
<dl className="space-y-3 text-sm">
  <div className="flex items-center justify-between gap-4">
    <dt className="text-muted-foreground">{t("status")}</dt>
    <dd>
      {isLoadingStatus ? <Skeleton className="h-5 w-16" /> : statusBadge}
    </dd>
  </div>
</dl>
```

After (`dl`/`dt`/`dd` are allowlisted and stay raw; the layout `div` becomes `Flex`):

```tsx
<dl className="space-y-3 text-sm">
  <Flex align="center" justify="between" gap="4">
    <dt className="text-muted-foreground">{t("status")}</dt>
    <dd>
      {isLoadingStatus ? <Skeleton className="h-5 w-16" /> : statusBadge}
    </dd>
  </Flex>
</dl>
```

**Import style:** extend the existing `import { ... } from "@fiestaboard/ui";` line in each file (98 files already have one).

**Per-file definition of done:** `grep -nE '<(div|span|p|h[1-6]|ul|ol|li|section|main|header|footer|nav|form|table|thead|tbody|tr|td|th|a|code|strong)\b' <file>` returns only react-router `Link` false-positives or nothing.

## Wave Task Template (Tasks 1–5 all follow this shape)

- [ ] **Step 1:** Create worktree + branch: `git worktree add .claude/worktrees/feat-primitives-wave-N -b feat-primitives-wave-N origin/main`
- [ ] **Step 2:** Apply the recipe to every file in the wave's list (below). Commit in chunks of 5–8 files: `git commit -m "refactor: migrate <area> to @fiestaboard/ui primitives (wave N)"`
- [ ] **Step 3:** Verify in Docker (from repo root): `docker compose -f docker-compose.dev.yml run --rm --profile test web sh -c "npm ci && npm run typecheck && npm run lint && npm run format:check && npm test"` → all PASS (run `npm run format` in-container and re-commit if format:check fails)
- [ ] **Step 4:** Build + run the branch image on `:4499`, screenshot every affected screen (before = same screens on `main`'s image), eyeball for unintended drift beyond the snapping table
- [ ] **Step 5:** Push, open PR titled `refactor: adopt FiestaUI primitives — wave N (<area>)`, attach screenshots, link the epic
- [ ] **Step 6:** After merge, delete the worktree: `git worktree remove .claude/worktrees/feat-primitives-wave-N`

### Task 1: Wave 1 — app root + routes (14 files)

**Files (Modify):** `web/app/root.tsx`, `web/app/routes/collections.tsx`, `web/app/routes/debug.tsx`, `web/app/routes/home.tsx`, `web/app/routes/integrations._index.tsx`, `web/app/routes/integrations.$pluginId.tsx`, `web/app/routes/login.tsx`, `web/app/routes/offline.tsx`, `web/app/routes/pages._index.tsx`, `web/app/routes/pages.edit._index.tsx`, `web/app/routes/picks.tsx`, `web/app/routes/schedule.tsx`, `web/app/routes/settings.tsx`, `web/app/routes/transitions.tsx`

Steps: template above. Screens to screenshot: `/`, `/login`, `/pages`, `/pages/edit`, `/integrations`, `/integrations/date_time`, `/schedule`, `/collections`, `/transitions`, `/picks`, `/settings`, `/debug`, `/offline`.
Note: `app/routes/debug.tsx` contains tables → `Table` set. `app/root.tsx` layout scaffolding that isn't covered by `MainContent`/`SkipToContent` chrome becomes `Box`.

### Task 2: Wave 2 — src/components top-level, A–O (20 files)

**Files (Modify):** `web/src/components/account-section.tsx`, `active-page-display.tsx`, `ai-action-confirmation.tsx`, `ai-chat-panel.tsx`, `board-display.tsx`, `board-size-indicator.tsx`, `boot-gate.tsx`, `chaining-mode-picker.tsx`, `chat-markdown.tsx`, `config-display.tsx`, `day-selector.tsx`, `drawable-board-preview.tsx`, `force-set-dialog.tsx`, `general-settings.tsx`, `global-ai-chat-drawer.tsx`, `home-assistant-entity-picker.tsx`, `inline-board-preview.tsx`, `install-prompt.tsx`, `navigation-sidebar.tsx`, `output-target-selector.tsx` (all under `web/src/components/`)

Steps: template above. Screens: dashboard, AI chat drawer, board preview states, navigation sidebar (desktop + mobile).
Note: board-display/drawable-board-preview have canvas/positioned hosts → `Box`, keep exact classes; do NOT snap board-geometry pixel values.

### Task 3: Wave 3 — src/components top-level, P–Z + i18n (20 files)

**Files (Modify):** `web/src/components/page-builder.tsx`, `page-editor-shell.tsx`, `page-grid-selector.tsx`, `page-picker-dialog.tsx`, `plain-text-editor.tsx`, `scaled-board-display.tsx`, `schedule-entry-form.tsx`, `service-controls.tsx`, `service-status.tsx`, `sidebar-account.tsx`, `silence-imminent-banner.tsx`, `silence-mode-status.tsx`, `smart-link.tsx`, `static-board-display.tsx`, `update-context.tsx`, `variable-autocomplete-textarea.tsx`, `variable-rule-row.tsx`, `version-display.tsx`, `wizard-provider.tsx` (under `web/src/components/`) plus `web/src/i18n/translations.tsx`

Steps: template above. Screens: page editor, schedule entry form, service status/controls (settings), account section.
Note: `smart-link.tsx` wraps router links — router `Link` stays; only plain `<a>` branches become `TextLink`.

### Task 4: Wave 4 — settings components (25 files)

**Files (Modify):** all 25 `web/src/components/settings/*.tsx`: `about-card.tsx`, `accessibility-settings.tsx`, `ai-settings.tsx`, `animation-settings.tsx`, `appearance-settings.tsx`, `auto-update-interval.tsx`, `backup-settings.tsx`, `beta-settings.tsx`, `board-settings.tsx`, `debug-settings.tsx`, `display-settings.tsx`, `festive-months-settings.tsx`, `instance-name.tsx`, `location-settings.tsx`, `mcp-settings.tsx`, `mqtt-settings.tsx`, `network-settings.tsx`, `plugin-settings.tsx`, `silence-schedule.tsx`, `system-controls.tsx`, `system-update.tsx`, `tile-grid-assignment.tsx`, `time-and-date.tsx`, `transition-settings.tsx`, `update-intervals.tsx`

Steps: template above. Screens: every `/settings` tab, light + dark.
Note: settings tables (backup list, debug info) → `Table` set; `about-card.tsx`'s `dl/dt/dd` stay raw per allowlist (worked example above).

### Task 5: Wave 5 — tiptap template editor (14 files)

**Files (Modify):** `web/src/components/tiptap-template-editor/TipTapTemplateEditor.tsx`, `components/ColorPickerContent.tsx`, `components/DrawCharPickerContent.tsx`, `components/FilterPickerContent.tsx`, `components/FormattingPickerContent.tsx`, `components/FormulaEditorPanel.tsx`, `components/TemplateEditorToolbar.tsx`, `components/ToolbarDropdown.tsx`, `components/VariablePickerContent.tsx`, `node-views/ColorTileNodeView.tsx`, `node-views/FillSpaceNodeView.tsx`, `node-views/FormulaNodeView.tsx`, `node-views/VariableNodeView.tsx`, `node-views/WrappedTextView.tsx`

Steps: template above. Screens: template editor with variables, formulas, color tiles, all toolbar pickers open; run draw-mode e2e specs.
Note: NodeViews render inside TipTap's contentEditable — character-grid geometry is pixel-load-bearing. Layout `div`s here that carry grid metrics keep exact classes via `Box className` (no snapping); only chrome around the editor normalizes.

### Task 6: Wave 6 — remainder + ESLint flip

**Files:**
- Modify: `web/src/components/wizard/setup-wizard.tsx`, `step-board-setup.tsx`, `step-easy-plugins.tsx`, `step-welcome.tsx`; `web/src/components/schedule/schedule-calendar-view.tsx`, `schedule-event.tsx`, `schedule-list-view.tsx`; `web/src/components/transitions/transition-grid-display.tsx`; `web/src/components/plugin-settings/schema-form.tsx`; `web/src/components/ui/sonner.tsx`, `time-picker.tsx`, `timezone-picker.tsx`
- Modify: `web/eslint.config.mjs`

- [ ] **Step 1–2:** Worktree + apply recipe to the 12 files (template above)
- [ ] **Step 3: Add the enforcement rule** — in `web/eslint.config.mjs`, append a new config object after the existing main block:

```js
// Design-system enforcement: app code renders @fiestaboard/ui components,
// not raw HTML. Allowlisted leaves (svg, canvas, iframe, img, br, em,
// small, kbd, pre, figure, dl, dt, dd) are simply not listed here.
{
  files: ["app/**/*.tsx", "src/**/*.tsx"],
  ignores: ["src/**/__tests__/**", "**/*.stories.tsx"],
  rules: {
    "react/forbid-elements": [
      "error",
      {
        forbid: [
          { element: "div", message: "Use Flex/Stack/Grid for layout, or Box (@fiestaboard/ui)" },
          { element: "span", message: 'Use Text as="span" (@fiestaboard/ui)' },
          { element: "p", message: "Use Text (@fiestaboard/ui)" },
          { element: "h1", message: "Use PageHeader (@fiestaboard/ui)" },
          { element: "h2", message: "Use Heading level={2} (@fiestaboard/ui)" },
          { element: "h3", message: "Use Heading level={3} (@fiestaboard/ui)" },
          { element: "h4", message: "Use Heading level={4} (@fiestaboard/ui)" },
          { element: "h5", message: "Use Heading (@fiestaboard/ui)" },
          { element: "h6", message: "Use Heading (@fiestaboard/ui)" },
          { element: "ul", message: "Use List (@fiestaboard/ui)" },
          { element: "ol", message: 'Use List as="ol" (@fiestaboard/ui)' },
          { element: "li", message: "Use ListItem (@fiestaboard/ui)" },
          { element: "section", message: 'Use Box as="section" (@fiestaboard/ui)' },
          { element: "main", message: 'Use MainContent or Box as="main" (@fiestaboard/ui)' },
          { element: "header", message: 'Use Box as="header" (@fiestaboard/ui)' },
          { element: "footer", message: 'Use Box as="footer" (@fiestaboard/ui)' },
          { element: "nav", message: 'Use Box as="nav" (@fiestaboard/ui)' },
          { element: "form", message: 'Use Box as="form" (@fiestaboard/ui)' },
          { element: "table", message: "Use Table (@fiestaboard/ui)" },
          { element: "thead", message: "Use TableHeader (@fiestaboard/ui)" },
          { element: "tbody", message: "Use TableBody (@fiestaboard/ui)" },
          { element: "tr", message: "Use TableRow (@fiestaboard/ui)" },
          { element: "th", message: "Use TableHead (@fiestaboard/ui)" },
          { element: "td", message: "Use TableCell (@fiestaboard/ui)" },
          { element: "a", message: "Use TextLink, or the router Link for navigation (@fiestaboard/ui)" },
          { element: "code", message: "Use Code (@fiestaboard/ui)" },
          { element: "strong", message: 'Use Text as="span" weight="semibold" (@fiestaboard/ui)' },
        ],
      },
    ],
  },
},
```

- [ ] **Step 4: Run lint expecting zero violations** — `docker compose -f docker-compose.dev.yml run --rm --profile test web sh -c "npm ci && npm run lint"`. Every hit is either a file missed by an earlier wave (fix it now, this is the sweep-up gate) or a legitimate `Box`/allowlist case.
- [ ] **Step 5:** Full Docker verify + screenshots (wizard, schedule views, transitions picker, toasts, time/timezone pickers)
- [ ] **Step 6:** Push, PR `refactor: adopt FiestaUI primitives — wave 6 (remainder) + forbid-elements rule`, link epic, note in the body that this closes the epic

---

## Epic Bookkeeping

Create the epic issue before Wave 1 (after the FiestaUI minor lands): title `Epic: adopt FiestaUI primitives — zero raw HTML in web app`, body = link to the spec + this plan + a checklist of the 6 waves. Each wave PR references it. Patterns that couldn't snap cleanly are logged as comments; recurring ones become FiestaUI issues.

## Self-Review Notes

- All 105 files from the raw-tag sweep are assigned to exactly one wave (14 + 20 + 20 + 25 + 14 + 12 = 105). Re-run the sweep grep at execution time and slot any newly-added files into the matching wave.
- The recipe table covers every element the lint rule bans; the allowlist matches the spec exactly.
- Interfaces: primitive names/props used in the recipe match the FiestaUI plan's Produces blocks (`Text` defaults `size="sm"`; `Heading` takes `level={2|3|4}`; `List` takes `as/marker/gap`; `Box` takes `as`).
- Known risk carried from the spec: if the evergreen upgrade PR mislabels `upgrade-blocked` (flaky baseline check), verify FiestaBoard CI directly and merge manually.
