// H5 per-formula values → FormulaAtom value hints (04c C1, "= 3 of 7 rows").
//
// Presentation-free: the caller formats `rows` with its own i18n. Every hint
// comes from the same render the board shows, so a chip never disagrees with
// the preview.

import type { FormulaDiagnostic, LineDiagnostic, RenderDiagnostics } from "@/lib/api/formula-debug";

export type AtomHintValue =
  { kind: "value"; text: string } | { kind: "rows"; shown: number; wanted: number } | { kind: "error"; tag: string };

export interface AtomHint {
  /** 1-based template line of the first formula with this source. */
  line: number;
  /** Its opening-brace offset (H7 trace selection). */
  start: number;
  value: AtomHintValue;
  state: "ok" | "error" | "fallback";
}

/** Longest value shown inside an atom before it is shortened. */
export const MAX_HINT_VALUE = 18;
const FALLBACK_CALL = /\b(DEFAULT|IFERROR|COALESCE)\s*\(/i;

/** The error tag a FormulaAtom shows: `#SYNTAX:n` carries its offset. */
export function errorTag(formula: Pick<FormulaDiagnostic, "error" | "error_at">): string | null {
  if (!formula.error) return null;
  if (formula.error === "#SYNTAX" && formula.error_at != null) return `#SYNTAX:${formula.error_at}`;
  return formula.error;
}

/** Normalize a formula body so the editor's expression and H5's `source` compare equal. */
export function normalizeSource(source: string): string {
  return source.trim();
}

function shorten(text: string): string {
  return text.length > MAX_HINT_VALUE ? `${text.slice(0, MAX_HINT_VALUE - 1)}…` : text;
}

/** Whether `source` reads any of `roots` (`root.` or `root:instance.`). */
export function readsAnyRoot(source: string, roots: readonly string[]): boolean {
  return roots.some((root) => rootPattern(root).test(source));
}

export function rootPattern(root: string): RegExp {
  const escaped = root.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(?<![\\w.])${escaped}(?::[\\w-]+)?\\.`);
}

/** The atom value for one formula, given its line's overflow report. */
export function atomValue(formula: FormulaDiagnostic, line?: LineDiagnostic | null): AtomHintValue {
  const tag = errorTag(formula);
  if (tag) return { kind: "error", tag };
  if (line && line.rows_wanted > 1 && formula.value.includes("\n")) {
    return { kind: "rows", shown: line.rows_shown, wanted: line.rows_wanted };
  }
  const first = formula.value.split("\n")[0] ?? "";
  return { kind: "value", text: first.length === 0 ? '""' : shorten(first) };
}

/**
 * The atom state. `fallback` marks a DEFAULT/IFERROR/COALESCE formula that
 * reads simulated-missing data and still produced a value (H6 Missing).
 */
export function atomState(formula: FormulaDiagnostic, missingRoots: readonly string[] = []): AtomHint["state"] {
  if (formula.error) return "error";
  if (missingRoots.length > 0 && FALLBACK_CALL.test(formula.source) && readsAnyRoot(formula.source, missingRoots)) {
    return "fallback";
  }
  return "ok";
}

/** Index H5 diagnostics by normalized formula source (first occurrence wins). */
export function buildHintIndex(
  diagnostics: RenderDiagnostics | null | undefined,
  missingRoots: readonly string[] = [],
): Map<string, AtomHint> {
  const index = new Map<string, AtomHint>();
  if (!diagnostics) return index;
  const lines = new Map<number, LineDiagnostic>();
  for (const line of diagnostics.lines ?? []) lines.set(line.line, line);
  for (const formula of diagnostics.formulas) {
    const key = normalizeSource(formula.source);
    if (index.has(key)) continue;
    index.set(key, {
      line: formula.line,
      start: formula.start,
      value: atomValue(formula, lines.get(formula.line)),
      state: atomState(formula, missingRoots),
    });
  }
  return index;
}

/** The H5 formula diagnostic for an editor expression, if the render saw it. */
export function findFormula(
  diagnostics: RenderDiagnostics | null | undefined,
  expression: string,
): FormulaDiagnostic | undefined {
  const key = normalizeSource(expression);
  return diagnostics?.formulas.find((formula) => normalizeSource(formula.source) === key);
}

/** The H5 line report for a template line. */
export function findLine(diagnostics: RenderDiagnostics | null | undefined, line: number): LineDiagnostic | undefined {
  return diagnostics?.lines?.find((entry) => entry.line === line);
}

/**
 * Whether any template line holds a `{{= … }}` formula atom, using the hub's
 * `_FORMULA_PATTERN` so only pages with real formulas ask a render for H5
 * diagnostics. Template text has no string syntax, so a `"` (an inch mark)
 * before the atom does not hide it.
 */
const FORMULA_ATOM = /\{\{=[^}{]*\}\}/;

export function templateHasFormula(template: readonly string[]): boolean {
  return template.some((line) => FORMULA_ATOM.test(line));
}

/**
 * `{{plugin.field}}` and `{{plugin:instance.field|filter}}` variable paths in a
 * template, in first-seen order (BB-FP-11). Formulas, colours and formatting
 * tokens have no `root.field` path and are skipped.
 */
const VARIABLE_TOKEN = /\{\{\s*([A-Za-z_][\w-]*(?::[\w-]+)?\.[\w.]+)\s*(?:\|[^{}]*)?\}\}/g;

export function templateVariablePaths(template: readonly string[]): string[] {
  const paths = new Set<string>();
  for (const line of template) for (const match of line.matchAll(VARIABLE_TOKEN)) paths.add(match[1]);
  return [...paths];
}

/**
 * One template line that evaluates each path as a formula, so the hub's H5
 * diagnostics report every variable's value in the preview's context.
 */
export function variableProbeTemplate(paths: readonly string[]): string[] {
  return [paths.map((path) => `{{= ${path} }}`).join(" ")];
}
