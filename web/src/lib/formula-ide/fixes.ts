// One-tap fixes from the inspector's clip report (04c C3, Android G3).

/** Split an argument list on commas outside strings and parentheses. */
export function splitTopLevelArgs(args: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let inString = false;
  let current = "";
  for (const ch of args) {
    if (inString) {
      current += ch;
      if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') inString = true;
    else if (ch === "(") depth++;
    else if (ch === ")") depth--;
    if (ch === "," && depth === 0) {
      parts.push(current.trim());
      current = "";
      continue;
    }
    current += ch;
  }
  if (current.trim()) parts.push(current.trim());
  return parts;
}

/** The index of the parenthesis closing the one at `open`, or -1. */
function closingParen(text: string, open: number): number {
  let depth = 0;
  let inString = false;
  for (let i = open; i < text.length; i++) {
    const ch = text[i];
    if (inString) {
      if (ch === '"') inString = false;
    } else if (ch === '"') inString = true;
    else if (ch === "(") depth++;
    else if (ch === ")" && --depth === 0) return i;
  }
  return -1;
}

/**
 * "Limit to N": set FOREACH's own row limit (its third argument) when the
 * whole formula is one FOREACH call; null otherwise.
 */
export function limitForeach(source: string, rows: number): string | null {
  const body = source.trim();
  const match = /^FOREACH\s*\(/i.exec(body);
  if (!match) return null;
  const open = match[0].length - 1;
  if (closingParen(body, open) !== body.length - 1) return null;
  const args = splitTopLevelArgs(body.slice(open + 1, -1));
  if (args.length < 2 || args.length > 3) return null;
  return `FOREACH(${[args[0], args[1], String(rows)].join(", ")})`;
}
