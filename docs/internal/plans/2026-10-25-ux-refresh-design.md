# FiestaBoard v10 UX refinement

The user supplied nine related UX issues and delegated choosing fixes and implementing them with cost-effective GPT-6.1 Sol subagents. This design records the proposed choices; these are implementation judgments, not claims that the user specified every detail.

## Intent

Make browsing, creating, and configuring displays feel coherent, focused, and usable on phones and desktops. Retain FiestaUI styling, existing content, and hardware behavior.

## Approach

Compose existing FiestaUI primitives in app-owned components. Alternatives considered were releasing new shared FiestaUI primitives first, or rebuilding the route/layout and settings architecture. Both increase scope unnecessarily: SectionShell already supplies headings, breadcrumbs and focus restoration, and existing device helpers support compatibility. Jev independently recommended app composition.

## Design decisions

1. **Display details:** organize configuration into clear sections/tabs so live preview, connection/setup, and playback controls do not form one unbounded form. Replace the transition card wall with a compact selector, selected description, and one demonstrative preview. Actual LED transitions use device-adjusted specs. Native split-flap demonstrations illustrate ordering and cadence. Deprecated plugins without a preview endpoint explicitly say preview is unavailable. Preserve None/default, unavailable/saved choices, cloud restrictions, speed persistence and reduced motion. Preview must never send to a device.
2. **Marketplaces:** compact responsive search/filter/view controls, counts and bounded results. Displays and Integrations share browsing patterns. Git installation opens from a secondary action rather than occupying a permanent large form. Preserve onboarding's existing display-catalog behavior.
3. **Pages:** consolidate toolbar and filters, remove duplicate local separators/padding. Filter by actual configured displays/compatible geometry and include LED/plugin displays. All pages and orphan shapes remain reachable. Page compatibility is not ownership; no schema migration.
4. **Collections:** tile/list modes with persistent preference. Tiles use resting stacked page previews inspired by the video CardStack; actual LED previews must preserve cells/layers/model. Limit previews to a few members and avoid preview work in list mode. Dedicated create/detail routes use SectionShell and share visual patterns with Pages. Keep ordered members, rules, custom duration, save/error handling and safe deletion. Add touch/keyboard reorder controls.
5. **Editor:** focused Text and Canvases modes for pixel-capable targets. Rich/plain stays within Text; Draw/Shapes/Source stays within Canvases. Shared name, save and preview/live controls remain accessible. Keep state through mode changes; canvas markers activate the correct mode and focus. Desktop uses editing/preview space effectively; mobile uses one main scroll area and a compact preview. Preserve unsupported-canvas notice and unsaved navigation protection.
6. **Plugin provenance:** Community badge for known repositories outside FiestaBoard's GitHub organization, including installed integrations and marketplace entries. Parse hostname/owner, not author text or string prefixes. Missing provenance stays unknown. Badge is attribution, not a safety endorsement.
7. **Integrations polish:** align marketplace conventions and reduce visual noise while preserving the existing successful layout, filters, update and install flows.
8. **Settings:** group compact settings by purpose and actual scope. Global app preview animation/flip speed remains global and is named clearly; device hardware transitions remain per-display. Move board-scoped silence controls into display details using explicit boardId, with discoverability/compatibility for existing settings links. Keep theme/language behavior, URL aliases, AI anchors, and other settings persistence. Use compact accessible selectors rather than custom incomplete radio controls.
9. **Account popup:** labeled popover around 304px wide, identity/account shortcut, compact theme selector, Settings/About, version/update status and separated sign-out. Preserve anonymous/collapsed states and mobile inline drawer controls; no nested popup over the mobile drawer.

## References

- Collection motif source: `../fiestaboard-media/studio/src/videos/h4-collections/helpkit.tsx`, CardStack.
- Video: `/Volumes/Video Projects/FiestaBoard/FiestaBoard Videos v2/3 Help videos/10 - Collections/Collections (4K) - corrected v2.mp4`.
- Existing app surfaces: `SectionShell`, `page-grid-selector`, `display-catalog`, `DisplayTransition`, `SidebarSettingsMenu`.

## Constraints and validation

Use @fiestaboard/ui 8.14.0 as declared, without modifying primitives or publishing another repository. Run dependencies/tests/runtime in isolated Docker containers; the existing fiestaboard-dev container belongs to the video project. No deployment or live-device writes are required. Avoid backend/schema changes unless essential to preserve existing behavior. Localize new UI copy. Verify focused behavior tests, typecheck/lint, then relevant integration and mobile/desktop visual checks. Cover draft retention, mismatched route/current board, unknown plugin source, orphan pages and reduced motion.
