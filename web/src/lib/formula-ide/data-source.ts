// Live · Sample · Missing and render-at (hub H6) for the page editor preview.
//
// Missing follows H6 exactly: every plugin the template reads is treated as
// unavailable, so variables render ??? and formulas reading them #REF unless
// DEFAULT/IFERROR/COALESCE catch it. Sample sends each integration's declared
// example values. `at` pins the formula clock only; plugin data is whatever
// the hub has cached.

import type { DataSource } from "@fiestaboard/ui";

import type { FormulaDiagnostic, PreviewSource, RenderPreviewContext } from "@/lib/api/formula-debug";

import { readsAnyRoot, rootPattern } from "./hints";

/** H6 caps `values` and `missing` at 64 entries each. */
export const MAX_PREVIEW_ENTRIES = 64;
const FALLBACK_CALL = /\b(DEFAULT|IFERROR|COALESCE)\s*\(/i;

/** Names formulas bind per item (FOREACH/FILTER/SORT); never plugin reads. */
const LOOP_LOCALS = new Set(["item"]);

/** The plugin ids a template reads, in `pluginIds` order. */
export function referencedRoots(template: readonly string[], pluginIds: readonly string[]): string[] {
  const text = template.join("\n");
  return pluginIds.filter((id) => !LOOP_LOCALS.has(id) && rootPattern(id).test(text));
}

interface ExampleMeta {
  type?: string;
  example?: string;
  format?: string;
}

/**
 * Sample values from each referenced plugin's declared scalar examples
 * (`GET /v1/variables` metadata). Roots with nothing to sample keep the hub's
 * own data and are reported in `unsampled`.
 */
export function sampleValues(
  metadata: Record<string, Record<string, ExampleMeta>> | undefined,
  roots: readonly string[],
): { values: Record<string, string>; unsampled: string[] } {
  const values: Record<string, string> = {};
  const unsampled: string[] = [];
  let count = 0;
  for (const root of roots) {
    let sampled = false;
    for (const [field, meta] of Object.entries(metadata?.[root] ?? {})) {
      if (count >= MAX_PREVIEW_ENTRIES) break;
      if (meta.type === "array" || meta.type === "color" || meta.format === "canvas") continue;
      if (typeof meta.example !== "string" || meta.example.length === 0) continue;
      values[`${root}.${field}`] = meta.example;
      count += 1;
      sampled = true;
    }
    if (!sampled) unsampled.push(root);
  }
  return { values, unsampled };
}

/**
 * The catalogue's metadata with each switched-off integration's declared
 * examples added (BB-E-12), so Sample can fill a plugin the hub leaves blank.
 */
export function withDisabledExamples(
  metadata: Record<string, Record<string, ExampleMeta>> | undefined,
  disabled: Record<string, { examples: Record<string, string> }> | undefined,
): Record<string, Record<string, ExampleMeta>> {
  const merged: Record<string, Record<string, ExampleMeta>> = { ...metadata };
  for (const [root, { examples }] of Object.entries(disabled ?? {})) {
    if (merged[root]) continue;
    merged[root] = Object.fromEntries(Object.entries(examples).map(([field, example]) => [field, { example }]));
  }
  return merged;
}

export interface PreviewContextInput {
  mode: DataSource;
  roots: readonly string[];
  sample: Record<string, string>;
  /** Naive ISO instant from {@link atIsoForTime}, or undefined for now. */
  at?: string | null;
}

/** The H6 `preview` object, or null when the ordinary live render applies. */
export function buildPreviewContext({ mode, roots, sample, at }: PreviewContextInput): RenderPreviewContext | null {
  const clock = at ? { at } : {};
  if (mode === "sample") return { values: sample, data: "cached", ...clock };
  if (mode === "missing") return { missing: roots.slice(0, MAX_PREVIEW_ENTRIES), data: "cached", ...clock };
  return at ? { at, data: "cached" } : null;
}

/** `HH:MM` today as a naive ISO instant (H6 reads naive as the hub's zone). */
export function atIsoForTime(hhmm: string, today: Date): string | null {
  const match = /^(\d{2}):(\d{2})$/.exec(hhmm);
  if (!match) return null;
  const pad = (n: number) => String(n).padStart(2, "0");
  const date = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;
  return `${date}T${match[1]}:${match[2]}:00`;
}

export interface MissingEntry {
  root: string;
  /** The first path the template reads under this root. */
  path: string;
  /** Freshness of the hub's own data (H6 `sources`); `none` when unreported. */
  state: PreviewSource["state"];
  updatedAt: string | null;
  /** Template lines whose `{{variable}}` renders ???. */
  variableLines: number[];
  /** Template lines whose formula fails (#REF) on it. */
  formulaLines: number[];
  /** Template lines whose DEFAULT/IFERROR/COALESCE fell back. */
  fallbackLines: number[];
}

function firstPath(template: readonly string[], root: string): string {
  const escaped = root.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(`(?<![\\w.])${escaped}(?::[\\w-]+)?(?:\\.\\w+)+`);
  for (const line of template) {
    const match = pattern.exec(line);
    if (match) return match[0];
  }
  return root;
}

function unique(values: number[]): number[] {
  return [...new Set(values)].sort((a, b) => a - b);
}

/** One entry per missing root: where it shows ???, #REF, or a fallback. */
export function missingReport({
  template,
  roots,
  formulas,
  sources,
}: {
  template: readonly string[];
  roots: readonly string[];
  formulas: readonly FormulaDiagnostic[];
  sources: Record<string, PreviewSource> | null | undefined;
}): MissingEntry[] {
  return roots.map((root) => {
    const pattern = rootPattern(root);
    const variableLines: number[] = [];
    template.forEach((line, index) => {
      for (const match of line.matchAll(/\{\{(?!=)([^}]*)\}\}/g)) {
        if (pattern.test(match[1].trim())) variableLines.push(index + 1);
      }
    });
    const reading = formulas.filter((formula) => readsAnyRoot(formula.source, [root]));
    return {
      root,
      path: firstPath(template, root),
      state: sources?.[root]?.state ?? "none",
      updatedAt: sources?.[root]?.updated_at ?? null,
      variableLines: unique(variableLines),
      formulaLines: unique(reading.filter((formula) => formula.error).map((formula) => formula.line)),
      fallbackLines: unique(
        reading
          .filter((formula) => !formula.error && FALLBACK_CALL.test(formula.source))
          .map((formula) => formula.line),
      ),
    };
  });
}

/** The designer's tip: wrap a missing path in DEFAULT to show `--` instead of ???. */
export function fallbackTip(path: string): string {
  return `DEFAULT(${path}, "--")`;
}
