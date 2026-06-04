Add a new plugin-settings form widget or schedule UX control.

Use the `widget-builder` agent. Required argument: the widget `<type>` (kebab-case, e.g. `enum-color`, `time-range`).

The agent will:
1. Verify a feature branch (`feat-widget-<type>`).
2. Read `web/src/components/plugin-settings/index.tsx` + `page-picker-field.tsx` as references.
3. Create `<type>-field.tsx`, register it for `ui:widget: "<type>"`, add Storybook story + Vitest test.
4. **Add every new i18n key to all 14 locale files** (`web/messages/*.json`).
5. Spot-check WCAG 2.2 AAA (focus ring, aria-label, contrast).
6. Update `plugins/CLAUDE.md` and `web/CLAUDE.md` widget lists.
7. Run type-check + Vitest inside the dev container.

If no `<type>` is provided, ask before proceeding.
