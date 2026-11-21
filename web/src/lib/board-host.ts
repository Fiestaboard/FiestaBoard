/**
 * A Vestaboard's Local API address, checked as the hub will check it
 * (`validate_board_host` in src/board_guards.py): a bare IPv4 address or
 * hostname, with no scheme, port, path or credentials. Catching a mistake
 * at the field (BB-C-15) beats a raw server error after "Test connection".
 */

// RFC 1123 labels joined by dots; a dotted-quad IPv4 address matches too.
const HOSTNAME =
  /^(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$/;

export type BoardHostProblem = "port" | "invalid";

/** Why *host* is not a usable board address, or `null` when it is (or is still empty). */
export function boardHostProblem(host: string): BoardHostProblem | null {
  if (!host) return null;
  if (/^[^:/@\s]+:\d*$/.test(host)) return "port";
  return HOSTNAME.test(host) ? null : "invalid";
}
