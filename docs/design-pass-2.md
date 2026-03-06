# FiestaBoard Design Pass 2 – Research & Plan (2025/2026)

This document summarizes research on what makes design good and modern in 2025/2026 and proposes a second design pass for the FiestaBoard web UI. It builds on the first pass (brand accent, type scale, empty states, dashboard hub, elevation, micro-interactions) and the removal of the mouse-follow spotlight effect.

---

## Research summary: What makes design good and modern (2025/2026)

### 1. Shift from trends to outcomes

Design is moving from “what’s possible?” to “what actually works?”—driven by data, user research, and business outcomes rather than pure aesthetics. Interfaces should feel purposeful and trustworthy, not gimmicky.

### 2. Performance as design

Speed is a design principle, not only an engineering concern. Perceived performance (skeleton states, instant feedback, minimal layout shift) matters as much as load time. Avoid heavy or distracting effects that don’t add clarity.

### 3. Hyper-minimalism and “barely-there” UI

Clean, light interfaces with limited color, simple typography, and confident use of space signal trust and focus. Users judge credibility in seconds; clutter and decorative effects can hurt that. Restraint and consistency beat visual noise.

### 4. Typography and readability

- **Scale:** Use a consistent type scale (e.g. 1.2–1.25 ratio). Body 16–18px desktop, 16px mobile; clear hierarchy for H1–H6.
- **Weights:** Limit to 2–3 weights; bold for emphasis, regular for body.
- **Line height:** 1.4–1.6× for body; line length 45–75 chars desktop, 35–50 mobile.
- **Spacing:** Consistent spacing tokens (e.g. 4/8px base); generous white space improves comprehension.

### 5. Accessibility-first

WCAG contrast (4.5:1+ for text), scalable type, focus indicators, and reduced-motion support are baseline expectations. Dark mode and high-contrast options support inclusivity.

### 6. Dashboard and control-panel patterns

- **F-pattern:** Most important content in top-left; clear visual hierarchy so key info stands out (e.g. “squint test”).
- **Progressive disclosure:** Essential info first; details on demand. Avoid overwhelming with everything at once.
- **Action-oriented:** Surfaces suggest “next best actions” and use strategic empty states with clear CTAs.
- **Consistency:** Uniform grid (e.g. 8px base), consistent colors and labels, 5–6 primary KPIs or actions per view.

### 7. Organic and humanized aesthetics

After years of strict grids, there’s a move toward softer shapes and flowing lines where it supports usability—without sacrificing clarity. The goal is “human-centric” balance: minimal restraint with enough warmth so the product doesn’t feel cold.

### 8. No cursor-chasing or distracting motion

Mouse-follow effects (e.g. spotlight that tracks the cursor) add little to clarity and can feel gimmicky or distracting. Modern, trustworthy UIs avoid them in favor of subtle, purposeful motion (e.g. hover state, page/section entrance).

---

## Changes already made (pre–Pass 2)

- **Mouse cursor effect removed:** SpotlightCard (mouse-follow gradient) removed from Dashboard and Integrations. Dashboard Active Display and Integrations plugin cards no longer use the spotlight; entrance animation and card styling remain.

---

## Proposed Design Pass 2 enhancements

These align with the research above and with the existing system in [`docs/design.md`](design.md).

### Tier A: Typography and spacing audit

1. **Type scale**
   - Lock in a single scale (e.g. 1.25) and document it in `docs/design.md`. Ensure body is 16px (or 1rem) and headings follow the scale.
   - Audit one-off `text-sm` / `text-base` / `text-lg` usages and replace with scale-based classes where it improves consistency.

2. **Line height and density**
   - Ensure body and descriptions use a comfortable line-height (e.g. `leading-relaxed` or 1.5). Check long copy (empty states, descriptions, Settings) for readability.
   - Optionally add a `.prose`-style utility for rare long-form text so line length and spacing are capped.

3. **Spacing system**
   - Confirm 8px (or 4px) base and use it consistently (e.g. `gap-4`, `space-y-6`, `p-6`). Document in `docs/design.md` and use in new components.

### Tier B: Dashboard and hierarchy

4. **Dashboard “5-second rule”**
   - Ensure the most important action or state (e.g. “Active Display”, “Change Page”, or setup CTA) is obvious at a glance. Consider a single primary CTA or status block in the top-left area of the main content.
   - Keep the existing hub gradient subtle; avoid re-adding cursor-based effects.

5. **Progressive disclosure**
   - On dense pages (e.g. Settings, Integrations), consider collapsible sections or tabs so the first view shows 5–6 main items and the rest are one click away. Align with existing accordions/cards where possible.

6. **Empty states as actions**
   - EmptyState already has a CTA; ensure copy is action-oriented (“Create your first page”, “Add an integration”) and that the button is the primary element. Optionally add a short “why” line to reduce friction.

### Tier C: Polish and accessibility

7. **Focus and interaction**
   - Audit focus-visible styles on buttons, links, and cards so keyboard users always see a clear ring. Ensure no custom motion (e.g. btn-lift) overrides or hides focus.
   - Keep `prefers-reduced-motion` handling for all motion (entrance, hover, lift).

8. **Contrast and dark mode**
   - Spot-check brand and sidebar-accent against background in light and dark; ensure text and borders meet WCAG AA. Tweak `--brand` or `--sidebar-accent` if needed.
   - Verify muted text and disabled states are readable in both themes.

9. **Skeleton and loading**
   - Where content is loaded asynchronously (Integrations, Pages grid, Settings), prefer skeleton placeholders over spinners so layout is stable and perceived performance is better. Expand use where it’s still spinner-only.

### Tier D: Optional (lower priority)

10. **Softer surfaces**
    - Consider slightly larger radius on key cards (e.g. dashboard card) or one consistent “hero” radius (e.g. `rounded-2xl`) for the main content card on Dashboard only—only if it doesn’t conflict with the existing system.

11. **Illustrated empty states**
    - Add a simple, on-brand SVG or image to EmptyState for “no pages” and “no integrations” to make first-run friendlier. Keep it minimal and avoid decoration for its own sake.

12. **Documentation**
    - Add a short “Design Pass 2” summary to `docs/design.md` (or link to this file) and note the removal of cursor effects and the principles above so future work stays aligned.

---

## Implementation order (suggested)

1. **Remove cursor effect** (done).
2. **Tier C (a11y and loading):** Focus audit, reduced-motion check, skeleton usage. Low risk, high impact.
3. **Tier A (typography and spacing):** Document scale and spacing; apply in a few high-traffic areas (Dashboard, Settings, EmptyState).
4. **Tier B (dashboard and hierarchy):** Single primary CTA or status check; optional progressive disclosure on Settings/Integrations.
5. **Tier D:** Optional radius/illustration/doc updates as time allows.

---

## Principles to keep

- **No mouse-follow or cursor-based effects** in the main UI.
- **Performance and clarity over decoration:** every effect should aid understanding or feedback.
- **Accessibility and reduced motion** are non-negotiable.
- **Consistency with existing tokens** in `globals.css` and `docs/design.md`; extend rather than replace.
