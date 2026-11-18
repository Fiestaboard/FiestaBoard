// The formula pretty-printer of the existing FormulaEditorPanel, extended to
// remember which source offsets land on each printed line, so H7 trace values
// can sit in the right margin of the line that produced them (04c C1).

import type { FormulaTraceEvent } from "@/lib/api/formula-debug";

export interface LineRange {
  /** First source offset printed on the line (UTF-16, the editor's units). */
  from: number;
  /** One past the last source offset printed on it. */
  to: number;
}

const INDENT = "  ";

/** Print a flat expression on indented lines; `lines[i]` maps printed line i back to the source. */
export function prettyPrint(expr: string): { text: string; lines: Array<LineRange | null> } {
  const out: string[] = [];
  const origin: number[] = [];
  let depth = 0;
  let inString = false;
  let skipSpaces = false;
  const emit = (text: string, source = -1) => {
    for (const ch of text) {
      out.push(ch);
      origin.push(source);
    }
  };

  for (let i = 0; i < expr.length; i++) {
    const ch = expr[i];
    if (inString) {
      emit(ch, i);
      if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') {
      inString = true;
      skipSpaces = false;
      emit(ch, i);
      continue;
    }
    if (skipSpaces && ch === " ") continue;
    skipSpaces = false;
    if (ch === "(") {
      depth++;
      emit(ch, i);
      emit("\n" + INDENT.repeat(depth));
      skipSpaces = true;
    } else if (ch === ")") {
      depth--;
      emit("\n" + INDENT.repeat(Math.max(depth, 0)));
      emit(ch, i);
    } else if (ch === ",") {
      emit(ch, i);
      emit("\n" + INDENT.repeat(depth));
      skipSpaces = true;
    } else {
      emit(ch, i);
    }
  }

  // Trim like the original printer: leading/trailing whitespace only.
  let start = 0;
  let end = out.length;
  while (start < end && /\s/.test(out[start])) start++;
  while (end > start && /\s/.test(out[end - 1])) end--;
  const text = out.slice(start, end).join("");

  const lines: Array<LineRange | null> = [];
  let current: LineRange | null = null;
  for (let k = start; k < end; k++) {
    if (out[k] === "\n" && origin[k] === -1) {
      lines.push(current);
      current = null;
      continue;
    }
    const source = origin[k];
    if (source < 0) continue;
    current = current
      ? { from: Math.min(current.from, source), to: Math.max(current.to, source + 1) }
      : { from: source, to: source + 1 };
  }
  lines.push(current);
  return { text, lines };
}

/** Collapse printed text back to one line (the original `unformatFormula`). */
export function flattenFormula(text: string): string {
  let result = "";
  let inString = false;
  let afterNewline = false;
  for (const ch of text) {
    if (inString) {
      result += ch;
      if (ch === '"') inString = false;
      afterNewline = false;
    } else if (ch === '"') {
      inString = true;
      result += ch;
      afterNewline = false;
    } else if (ch === "\n") {
      afterNewline = true;
    } else if (ch === " " && afterNewline) {
      // indentation
    } else {
      result += ch;
      afterNewline = false;
    }
  }
  // A printed call puts ", " back as "," + newline; restore the space.
  return result.replace(/,(?=\S)/g, (match, offset: number) => (insideString(result, offset) ? match : ", ")).trim();
}

function insideString(text: string, offset: number): boolean {
  let quotes = 0;
  for (let i = 0; i < offset; i++) if (text[i] === '"') quotes++;
  return quotes % 2 === 1;
}

function spanKey(event: Pick<FormulaTraceEvent, "start" | "end">): string {
  return `${event.start}:${event.end}`;
}

/** Occurrences of each source span, in execution order. Loops repeat spans. */
export function occurrences(events: readonly FormulaTraceEvent[]): Map<string, FormulaTraceEvent[]> {
  const bySpan = new Map<string, FormulaTraceEvent[]>();
  for (const event of [...events].sort((a, b) => a.id - b.id)) {
    const key = spanKey(event);
    const list = bySpan.get(key);
    if (list) list.push(event);
    else bySpan.set(key, [event]);
  }
  return bySpan;
}

/** How many loop iterations the trace recorded (1 when nothing repeats). */
export function iterationCount(events: readonly FormulaTraceEvent[]): number {
  let count = 1;
  for (const list of occurrences(events).values()) count = Math.max(count, list.length);
  return count;
}

/** The occurrence of a span for a 0-based iteration (the last one if it ran fewer times). */
export function pickOccurrence<T>(list: readonly T[], iteration: number): T {
  return list[Math.min(Math.max(iteration, 0), list.length - 1)];
}

/**
 * One margin value per printed line: the outermost non-literal step that
 * starts on that line, for the chosen loop iteration. The root step is the
 * atom's own value and stays out of the margin.
 */
export function lineValueHints(
  events: readonly FormulaTraceEvent[],
  lines: ReadonlyArray<LineRange | null>,
  iteration: number,
): Array<string | null> {
  const spans = [...occurrences(events).values()]
    .map((list) => pickOccurrence(list, iteration))
    .filter((event) => event.kind !== "literal" && event.parent !== null);
  return lines.map((range) => {
    if (!range) return null;
    let best: FormulaTraceEvent | null = null;
    for (const event of spans) {
      if (event.start < range.from || event.start >= range.to) continue;
      if (!best || event.end - event.start > best.end - best.start) best = event;
    }
    if (!best) return null;
    return best.error ?? best.value;
  });
}
