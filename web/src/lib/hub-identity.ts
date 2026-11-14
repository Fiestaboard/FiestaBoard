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

/** Whether *hostname* names the home network or a remote address. */
export function hubHostKind(hostname: string): HubHostKind {
  const host = hostname.trim().toLowerCase().replace(/\.$/, "");
  if (host === "localhost" || host === "[::1]" || host === "::1" || host === "127.0.0.1") return "local";
  if (host.endsWith(".local")) return "local";
  if (lanHintHost(host) !== null) return "local";
  // A single-label name ("fiestapi") only resolves on the LAN.
  if (!host.includes(".") && !host.includes(":")) return "local";
  return "remote";
}

/**
 * The state the hub line shows. `undefined` until the host is known (the
 * BoardSelector then renders no hub line at all).
 */
export function hubLineStatus({
  host,
  hubReachable,
  deviceOnline,
}: {
  host: string;
  hubReachable: boolean;
  deviceOnline: boolean;
}): BoardSelectorHubStatus | undefined {
  if (!host) return undefined;
  if (!deviceOnline || !hubReachable) return "unreachable";
  return hubHostKind(host) === "local" ? "online" : "remote";
}
