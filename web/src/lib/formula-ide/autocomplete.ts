// Code-mode autocomplete over the hub's real built-ins (`GET /v1/functions`).

import type { FunctionSignatureEntry } from "@/lib/api/templates";

export interface FunctionMatch extends FunctionSignatureEntry {
  name: string;
}

function insideString(text: string): boolean {
  let quotes = 0;
  for (const ch of text) if (ch === '"') quotes++;
  return quotes % 2 === 1;
}

/** The identifier being typed before `pos`, unless the caret is in a string or a variable path. */
export function completionContext(text: string, pos: number): { from: number; word: string } | null {
  const before = text.slice(0, pos);
  if (insideString(before)) return null;
  const match = /[A-Za-z_][A-Za-z0-9_]*$/.exec(before);
  if (!match) return null;
  const from = pos - match[0].length;
  if (from > 0 && /[.\w]/.test(before[from - 1])) return null;
  return { from, word: match[0] };
}

/** Built-ins whose name starts with `word` (any case), by name. */
export function matchFunctions(
  word: string,
  functions: Record<string, FunctionSignatureEntry> | undefined,
): FunctionMatch[] {
  if (!word) return [];
  const prefix = word.toUpperCase();
  return Object.entries(functions ?? {})
    .filter(([name]) => name.startsWith(prefix))
    .map(([name, entry]) => ({ name, ...entry }))
    .sort((a, b) => a.name.localeCompare(b.name));
}
