import type { BoardTokenJson, CharsetIssue } from "@/lib/api";

/**
 * A board token as the page editor writes it, for a charset warning: a
 * character as itself (a space as "␣", so it is visible), a colour tile as
 * its `{code}` shortcut, an icon by name.
 */
export function charsetTokenText(token: BoardTokenJson): string {
  if (token.icon) return `{${token.icon}}`;
  if (token.type === "color") return `{${token.code ?? ""}}`;
  const value = token.value ?? "";
  return value === " " ? "␣" : value;
}

/**
 * The cells a board really draws differently: everything but lowercase it
 * shows in capitals (`reason: "case"`), which every split-flap board does and
 * loses nothing. Text from data ("Launch") gave one warning per letter (BB-B-7).
 */
export function drawnDifferently(issues: readonly CharsetIssue[] | null | undefined): CharsetIssue[] {
  return (issues ?? []).filter((issue) => issue.reason !== "case");
}
