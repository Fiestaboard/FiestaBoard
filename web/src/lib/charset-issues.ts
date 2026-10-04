import type { BoardTokenJson } from "@/lib/api";

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
