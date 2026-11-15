/**
 * The hub line under the BoardSelector (WEB-09; 07a `302:2146`, 07 `53:143037`):
 * the address this page was opened at, and whether that is the home network,
 * a remote address, or a hub this browser cannot reach right now.
 *
 * The hub does not name a "remote address" setting, so the line reads the
 * address the user is actually using: a LAN name (`*.local`, a single-label
 * name, `localhost`) or a private IPv4 address is the home network; anything
 * else reached the hub from outside it (a VPN or tunnel name, a public host).
 */
import type { BoardSelectorHubStatus } from "@fiestaboard/ui";

import { lanHintHost } from "@/lib/network-hint";

export type HubHostKind = "local" | "remote";

/** Private-use suffixes that only resolve on a home network (RFC 6762, RFC 8375, common router defaults). */
const LAN_SUFFIXES = [".local", ".lan", ".home.arpa", ".internal", ".localdomain", ".home"];

/** Whether an IPv6 literal (with or without brackets) is loopback, unique-local (fc00::/7) or link-local (fe80::/10). */
function isLocalIpv6(host: string): boolean {
  const bare = host.replace(/^\[|\]$/g, "").split("%")[0];
  if (!bare.includes(":")) return false;
  if (bare === "::1") return true;
  const first = parseInt(bare.split(":")[0] || "0", 16);
  if (Number.isNaN(first)) return false;
  return (first & 0xfe00) === 0xfc00 || (first & 0xffc0) === 0xfe80;
}

/** Whether *hostname* names the home network or a remote address. */
export function hubHostKind(hostname: string): HubHostKind {
  const host = hostname.trim().toLowerCase().replace(/\.$/, "");
  if (host === "localhost" || host.endsWith(".localhost")) return "local";
  // 127.0.0.0/8 is all loopback.
  if (/^127\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(host)) return "local";
  if (isLocalIpv6(host)) return "local";
  if (LAN_SUFFIXES.some((suffix) => host.endsWith(suffix))) return "local";
  if (lanHintHost(host) !== null) return "local";
  // A single-label name ("fiestapi") only resolves on the LAN.
  if (!host.includes(".") && !host.includes(":")) return "local";
  // Everything else reached the hub from outside: a public name or address,
  // a VPN/tunnel name (Tailscale's *.ts.net and 100.64/10 included) and, with
  // no hub field to say otherwise, a split-DNS name used at home (DD-W39).
  return "remote";
}

/**
 * The state the hub line shows. `undefined` until the host is known, or
 * until the hub has answered or failed once: a state is only claimed when
 * it is known (the BoardSelector then draws no dot or word).
 */
export function hubLineStatus({
  host,
  hubReachable,
  hubKnown = true,
  deviceOnline,
}: {
  host: string;
  hubReachable: boolean;
  hubKnown?: boolean;
  deviceOnline: boolean;
}): BoardSelectorHubStatus | undefined {
  if (!host) return undefined;
  if (!deviceOnline) return "unreachable";
  if (!hubKnown) return undefined;
  if (!hubReachable) return "unreachable";
  return hubHostKind(host) === "local" ? "online" : "remote";
}
