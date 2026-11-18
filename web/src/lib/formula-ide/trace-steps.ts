// H7 trace events → FiestaUI TraceStep rows (04c C3 Steps; 07c phone Inspect sheet).

import type { FormulaTrace, FormulaTraceEvent } from "@/lib/api/formula-debug";

import { occurrences, pickOccurrence } from "./pretty";

export interface TraceStepRow {
  id: number;
  /** The authored sub-expression, sliced from the formula body. */
  expression: string;
  /** Its value, or its error tag. */
  value: string;
  state: "ok" | "error";
  /** Nesting below the formula's root step. */
  depth: number;
}

/** Slice by Unicode code points: H7 spans are code-point offsets. */
export function sliceCodePoints(text: string, start: number, end: number): string {
  return Array.from(text).slice(start, end).join("");
}

/**
 * Executed steps for one loop iteration, each step after the steps it
 * depended on (the order values were known). Literals are left out: their
 * value is their text.
 */
export function traceSteps(trace: Pick<FormulaTrace, "source" | "events">, iteration: number): TraceStepRow[] {
  // Keep one occurrence of every repeated span: the chosen iteration.
  const kept = new Map<number, FormulaTraceEvent>();
  for (const list of occurrences(trace.events).values()) {
    const event = pickOccurrence(list, iteration);
    kept.set(event.id, event);
  }
  // A kept event whose parent was dropped belongs to another iteration.
  const included = new Map<number, FormulaTraceEvent>();
  const isIncluded = (event: FormulaTraceEvent): boolean => {
    if (event.parent === null) return true;
    const parent = kept.get(event.parent);
    return parent !== undefined && isIncluded(parent);
  };
  for (const event of kept.values()) if (isIncluded(event)) included.set(event.id, event);

  const depthOf = (event: FormulaTraceEvent): number =>
    event.parent === null ? 0 : 1 + depthOf(included.get(event.parent)!);

  const rows: TraceStepRow[] = [];
  const visit = (event: FormulaTraceEvent) => {
    const children = [...included.values()].filter((child) => child.parent === event.id).sort((a, b) => a.id - b.id);
    children.forEach(visit);
    if (event.kind === "literal") return;
    rows.push({
      id: event.id,
      expression: sliceCodePoints(trace.source, event.start, event.end).trim(),
      value: event.error ?? event.value,
      state: event.error ? "error" : "ok",
      depth: depthOf(event),
    });
  };
  [...included.values()]
    .filter((event) => event.parent === null || !included.has(event.parent))
    .sort((a, b) => a.id - b.id)
    .forEach(visit);
  return rows;
}
