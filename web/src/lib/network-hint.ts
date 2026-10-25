/**
 * The network hint (`hint_host`): the browser's LAN address, sent with every
 * scan so an output searches the right network.
 *
 * FiestaBoard usually runs in Docker bridge mode, where the server's own
 * address (`172.x`) names a container network, not the LAN the device is on.
 * The address the user typed to open FiestaBoard does name it — when that is
 * a private IPv4 address. A hostname (`fiestaboard.local`), `localhost`, a
 * public address or IPv6 says nothing reliable, so no hint is sent.
 */
import type { OutputActionDescriptor } from "@/lib/api";

/** The generic action input core hands to a scan (`src/outputs/hooks.py` `HINT_HOST`). */
export const HINT_HOST = "hint_host";

/** The action input a user may fill to name the network to search. */
export const SUBNET = "subnet";

const PRIVATE_IPV4: ReadonlyArray<(octets: number[]) => boolean> = [
  ([a]) => a === 10,
  ([a, b]) => a === 172 && b >= 16 && b <= 31,
  ([a, b]) => a === 192 && b === 168,
  ([a, b]) => a === 169 && b === 254,
];

/** *hostname* when it is a private (RFC 1918) or link-local IPv4 address, else `null`. */
export function lanHintHost(hostname: string | null | undefined): string | null {
  const match = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(hostname ?? "");
  if (!match) return null;
  const octets = match.slice(1).map(Number);
  if (octets.some((octet) => octet > 255)) return null;
  return PRIVATE_IPV4.some((test) => test(octets)) ? octets.join(".") : null;
}

/** The hostname this page was opened at (`""` outside a browser). */
export function browserHostname(): string {
  return typeof window === "undefined" ? "" : window.location.hostname;
}

/** Whether *action*'s `input_schema` declares the input *name*. */
export function declaresInput(action: OutputActionDescriptor, name: string): boolean {
  const properties = action.input_schema?.properties;
  return typeof properties === "object" && properties !== null && name in properties;
}

/** Whether running *action* is a scan the hint helps: `discover`, an action declaring `hint_host`, or a device picker's. */
export function isScan(action: OutputActionDescriptor, fromPicker = false): boolean {
  return fromPicker || action.id === "discover" || declaresInput(action, HINT_HOST);
}

/**
 * *input* with `hint_host` set to *hint* when *action* is a scan and the
 * input has none; otherwise *input* unchanged (`undefined` stays `undefined`).
 */
export function withNetworkHint(
  action: OutputActionDescriptor,
  input: Record<string, unknown> | undefined,
  hint: string | null,
  fromPicker = false,
): Record<string, unknown> | undefined {
  if (hint === null || !isScan(action, fromPicker)) return input;
  const given = input?.[HINT_HOST];
  if (given !== undefined && given !== null && given !== "") return input;
  return { ...input, [HINT_HOST]: hint };
}
