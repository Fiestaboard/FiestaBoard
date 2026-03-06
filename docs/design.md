# FiestaBoard Web UI – Design Tokens and Conventions

This document describes the design tokens and usage conventions for the FiestaBoard web app (`web/`). It helps keep UI changes consistent and clarifies when to use which tokens.

## Where tokens live

- **Theme and tokens:** [`web/src/app/globals.css`](../web/src/app/globals.css)  
  - `@theme inline { ... }` – maps CSS variables into Tailwind v4 utilities.  
  - `:root` – light theme semantic and elevation variables.  
  - `.dark` – dark theme overrides.

## Contrast and accessibility

Semantic colors are chosen for WCAG AA contrast where text is used: primary-foreground on primary, sidebar-accent-foreground on sidebar-accent, brand-foreground on brand. Muted-foreground is used for secondary text on background/card and meets contrast in both light and dark themes. Spot-check new tokens (e.g. after Design Pass 2) in both themes.

## Semantic colors

Use these for UI chrome, not for board tile colors.

| Token (Tailwind)   | CSS variable   | Use |
|--------------------|----------------|-----|
| `background`       | `--background` | Page and app background |
| `foreground`       | `--foreground` | Primary text |
| `card` / `card-foreground` | `--card`, `--card-foreground` | Card surfaces and text |
| `primary` / `primary-foreground` | `--primary`, `--primary-foreground` | Buttons, active controls, emphasis |
| `secondary` / `secondary-foreground` | `--secondary`, `--secondary-foreground` | Secondary buttons, tabs |
| `muted` / `muted-foreground` | `--muted`, `--muted-foreground` | Muted backgrounds and secondary text |
| `accent` / `accent-foreground` | `--accent`, `--accent-foreground` | Hover states, highlights |
| `brand` / `brand-foreground` | `--brand`, `--brand-foreground` | Sidebar active state, key links, accent UI |
| `destructive` / `destructive-foreground` | `--destructive`, `--destructive-foreground` | Delete, errors, danger |
| `border`, `input`, `ring` | `--border`, `--input`, `--ring` | Borders, inputs, focus rings |

**Sidebar:** `sidebar`, `sidebar-foreground`, `sidebar-primary`, `sidebar-accent`, `sidebar-border`, `sidebar-ring` – use for the navigation sidebar only.

**Status:** `info`, `success`, `warning` (and `-foreground`) – use for status messages and badges.

## Type scale

- **Ratio:** 1.25. Body text 16px (1rem). Use Tailwind `text-*` from the scale (xs 0.75rem, sm 0.875rem, base 1rem, lg 1.125rem, xl 1.25rem, 2xl 1.5rem, 3xl 1.875rem, 4xl 2.25rem). Headings should use scale-based or semantic classes below.
- **Page title:** `.page-title` – `text-2xl sm:text-3xl font-bold tracking-tight`  
  Use for main heading on list/detail pages (Pages, Settings, Integrations, etc.).
- **Page description:** `.page-description` – `text-muted-foreground mt-1 text-sm sm:text-base`  
  Use for the one-line description under the page title.
- **Display title (hub):** `.page-title-display` – `text-3xl sm:text-4xl font-bold tracking-tight`  
  Use for the Dashboard (home) title only.

Font families: `--font-sans` (Geist Sans), `--font-mono` (Geist Mono). Set in layout and mapped in `@theme`.

## Spacing and radius

- **Spacing:** 8px base unit. Prefer `gap-4`, `space-y-6`, `p-4`/`p-6` for sections and cards.
- **Radius:** `--radius` (base), and Tailwind `radius-sm` through `radius-4xl` (derived).  
  Cards use `rounded-xl`; buttons and inputs use `rounded-md`.
- **Containers:** `container mx-auto` with responsive padding: `px-3 sm:px-4 md:px-6 py-4 sm:py-6 md:py-8`.
- **Sections:** `space-y-6 sm:space-y-8` between major sections; `mb-4 sm:mb-6` under page headers.

## Elevation (shadows)

- **Cards:** `shadow-card` (utility from `--shadow-card` / `--elevation-card`).  
  Use for `Card` and card-like surfaces.
- **Modals / sheets:** `shadow-modal` (from `--shadow-modal` / `--elevation-modal`).  
  Use for Sheet, dialogs, and overlay panels.

Values are theme-aware: lighter in light mode, slightly stronger in dark mode.

## Board colors vs UI colors

**Do:**

- Use **board colors** (`--color-board-red`, `-orange`, `-yellow`, `-green`, `-blue`, `-violet`, `-white`, `-black`) and board surface/bezel tokens only for:
  - Board tile content and previews.
  - Schedule/calendar event colors.
  - Status indicators that mirror board state (e.g. service status dot).
- Use **semantic UI tokens** (`primary`, `accent`, `muted`, `brand`, `destructive`, etc.) for:
  - Buttons, links, nav, form controls.
  - Cards, borders, backgrounds, text.

**Don’t:**

- Don’t use board colors for generic UI (buttons, nav, cards, links).  
  Use `primary`, `brand`, or `accent` instead.
- Don’t use semantic UI tokens for the actual board tile rendering or schedule event colors.  
  Use the board palette so the UI matches what appears on the physical display.

## Micro-interactions

- **CTA lift:** `.btn-lift` – subtle `scale(1.02)` on hover and `scale(0.98)` on active for primary CTAs (e.g. “Run Setup Wizard”, “New” on Pages).  
  Respects `prefers-reduced-motion` (no scale when reduced motion is preferred).
- Keep default focus-visible rings (`ring`, `ring-ring`) for accessibility.

## Empty states

Use the shared `EmptyState` component (`web/src/components/ui/empty-state.tsx`) with an icon, title, optional description, and optional CTA for “no pages”, “no carousels”, and similar list-empty cases. Keeps copy and layout consistent and makes it easy to add illustrations later.

## Animation

- **Page entrance:** `animate-card-fade-in` with optional `animationDelay` for staggered sections (e.g. Settings, Pages, Integrations).
- **Reduced motion:** All custom animations and `.btn-lift` are overridden or disabled when `prefers-reduced-motion: reduce` is set in `globals.css`.

## Design Pass 2

A second design pass (2025/2026) applied accessibility, typography, hierarchy, and loading improvements. See [Design Pass 2](design-pass-2.md) for the full plan and research. Principles: no mouse-follow or cursor-based effects in the main UI; performance and clarity over decoration; accessibility and reduced motion are non-negotiable; extend existing tokens, don’t replace.

## Design Pass 3 – Neutral Palette and Surface Consistency

A third design pass (2026) focused on two areas:

### Achromatic neutral palette

All neutral surface tokens (`background`, `card`, `muted`, `secondary`, `accent`, `border`, `input`, `ring`, and sidebar equivalents) were switched from warm-tinted oklch values (hue 80, low chroma) to true achromatic neutrals (hue 0, chroma 0). This removes the creamy/beige cast that made the UI feel dated and eliminates the visual disconnect between warm-tinted backgrounds and pure-white cards.

Light mode `--background` was also lowered slightly (0.995 to 0.985) to create a “barely-there gray” page surface, giving white cards a clean, intentional contrast without relying on heavy shadows.

Dark mode card-to-background lightness gap was tightened (from 0.06 to 0.03) for subtler surface differentiation, relying more on borders and elevation shadows. All warm hue remnants in dark mode elevation shadows were also neutralized.

Brand warmth continues to come from the orange accent (`--brand`) and board palette colors, not from tinting every surface.

### Surface consistency

The Settings page was refactored from custom `bg-muted/20` / `bg-muted/30` rounded sections to standard `Card` components, matching the surface treatment used on all other pages (Pages, Carousels, Integrations, Schedule). Redundant section titles that duplicated titles already inside child Card components were removed.

Hardcoded warm oklch values in `.card-interactive:hover` were replaced with achromatic neutrals.
