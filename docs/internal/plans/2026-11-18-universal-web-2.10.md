# Universal web 2.10 — Formulas and debugging (04c)

Branch `feat/universal-web-2.10-formulas`, stacked on `feat/universal-web-2.5-editor-touch`.
FiestaUI `8.17.0-alpha.3` (C30 ChoiceChip, C31 FormulaAtom, C32 TraceStep, C33 DataSourceSwitch).
Hub: H5 `diagnostics`, H6 `preview` + `sources`, H7 `debug.trace` / `debug.source_map` on `POST /templates/render`.

## Figma refs (shots/web-2.10/FIGMA-REFS.md)

- 04c `111:30911` Code mode with autocomplete and inline value hints (1440).
- 04c `118:5246` Builder, list recipe, column budget (1440).
- 04c `132:20145` Inspect: click a cell → source, Steps, clip report (1440).
- 07c `307:46094` / `316:97494` H6 Missing at 1440 / 900 with render-at.
- 07c `307:45424` 390 long-press chip › Inspect bottom sheet (TraceStep per ruling).

## Design

Pure logic (`web/src/lib/formula-ide/*`, unit tested first):

- `api` client additions: `formulaDebugApi.render()` (diagnostics, preview, debug).
- `hints`: H5 formula/line diagnostics → FormulaAtom value/state per formula source.
- `data-source`: Live/Sample/Missing + render-at → H6 `preview` object; referenced plugin roots;
  sample values from `/v1/variables` examples; missing report from H5 errors + H6 sources.
- `pretty`: offset-tracking pretty printer; trace events → right-margin value hints per line,
  stepping through FOREACH iterations (‹ n of m ›).
- `autocomplete`: prefix matching over `/v1/functions` (real built-ins only).
- `recipes`: the six Builder recipes writing plain formula text; list column budget.
- `trace-steps`: H7 events → TraceStep rows (expression, value, state, depth).
- `source-map`: H7 cell → source, formula, FOREACH row index, cells to outline.

UI (`web/src/components/formula-ide/*`, lazy where heavy):

- Context + hook mounted by PageBuilder with minimal seams (render target, preview props,
  board click, docked workbench slot, overlays).
- Desktop (≥1024): docked Formula card (Code | Builder via Tabs), "Line N produces" card,
  Inspector pane (Value | Steps | Width) with TraceStep and clip report, Inspect toggle (I).
- All widths: DataSourceSwitch + render-at TimePicker; Missing values card; Sample header.
- 390: long-press (or context-menu key) on a formula chip → Inspect bottom Sheet with TraceStep.
- FormulaNodeView shows FormulaAtom value hints when the IDE provider is present.

## Tests

Vitest for every lib module and the components; Playwright layout spec
`web/tests/layout/formula-ide.spec.ts` at 390/900/1440 light+dark with axe (hosted CI).
14 locales with identical `formulaIde` keys.
