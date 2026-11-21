import type { CharsetIssue } from "@/lib/api";
import type { BoardValidationCode, BoardValidationError } from "@/lib/api/page-history";
import { drawnDifferently } from "@/lib/charset-issues";

export type IdeProblemKind = BoardValidationCode | "substitution";

/** One row of the Problems / Warnings console, before localization. */
export interface IdeProblem {
  id: string;
  severity: "error" | "warning";
  kind: IdeProblemKind;
  /** 1-based template line, when the problem has a source location. */
  line: number | null;
  /** Hub wording (H4 validate) or the substitution itself ("é → E"). */
  message: string;
}

/** Every H4 board-width validation error is an error: the board would show the page wrong. */
export function problemsFromValidation(errors: readonly BoardValidationError[]): IdeProblem[] {
  return errors.map((error, index) => ({
    id: `validate-${index}-${error.line}-${error.column}-${error.code}`,
    severity: "error",
    kind: error.code,
    line: error.line,
    message: error.message,
  }));
}

function tokenText(token: CharsetIssue["token"]): string {
  if (token.type === "color") return `{${token.code ?? ""}}`;
  return token.value ?? "";
}

/**
 * Charset substitutions at the target board (render `charset_issues`) are
 * warnings: the page still shows, with "é" drawn as "E". One row per distinct
 * substitution on a row, so a repeated letter is not twenty warnings.
 */
export function warningsFromCharset(issues: readonly CharsetIssue[] | null | undefined): IdeProblem[] {
  const seen = new Set<string>();
  const warnings: IdeProblem[] = [];
  for (const issue of drawnDifferently(issues)) {
    const message = `${tokenText(issue.token)} → ${tokenText(issue.fallback)}`;
    const key = `${issue.row}:${message}`;
    if (seen.has(key)) continue;
    seen.add(key);
    warnings.push({ id: `charset-${key}`, severity: "warning", kind: "substitution", line: issue.row + 1, message });
  }
  return warnings;
}

/** Substitutions summarized for the Sent line ("1 substitution (é → E)"). */
export function substitutionSummary(warnings: readonly IdeProblem[]): string[] {
  return [...new Set(warnings.filter((w) => w.kind === "substitution").map((w) => w.message))];
}
