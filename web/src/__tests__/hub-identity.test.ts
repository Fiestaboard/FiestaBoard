/**
 * The BoardSelector hub line (07a `302:2146`): "host · Online / Remote / Can't reach".
 */
import { describe, expect, it } from "vitest";

import { hubHostKind, hubLineStatus } from "@/lib/hub-identity";

describe("hubHostKind", () => {
  it.each(["fiestapi.local", "FIESTAPI.LOCAL", "localhost", "fiestapi", "192.168.1.20", "10.0.0.4", "172.20.1.1"])(
    "reads %s as the home network",
    (host) => {
      expect(hubHostKind(host)).toBe("local");
    },
  );

  it.each(["fiestapi.example.net", "board.example.com", "8.8.8.8", "fiestapi.tail1234.ts.net"])(
    "reads %s as a remote address",
    (host) => {
      expect(hubHostKind(host)).toBe("remote");
    },
  );

  it.each([
    "fiestapi.lan",
    "fiestapi.home.arpa",
    "fiestapi.internal",
    "fiestapi.localdomain",
    "fiestapi.home",
    "127.0.1.1",
    "127.10.20.30",
    "hub.localhost",
    "[::1]",
    "[fd12:3456:789a::1]",
    "[fc00::5]",
    "[fe80::1c2b:3cff:fe4d:5e6f]",
    "169.254.10.20",
  ])("reads %s (home-network suffix, loopback or private/link-local IP) as local", (host) => {
    expect(hubHostKind(host)).toBe("local");
  });

  it.each(["100.101.102.103", "[2001:db8::1]", "fiestapi.example.lan.com", "homeassistant.ui.nabu.casa"])(
    "keeps %s (Tailscale CGNAT, a public IPv6, a public name) remote",
    (host) => {
      expect(hubHostKind(host)).toBe("remote");
    },
  );
});

describe("hubLineStatus", () => {
  it("is Online on the home network while the hub answers", () => {
    expect(hubLineStatus({ host: "fiestapi.local", hubReachable: true, deviceOnline: true })).toBe("online");
  });

  it("is Remote on a remote address while the hub answers", () => {
    expect(hubLineStatus({ host: "fiestapi.example.net", hubReachable: true, deviceOnline: true })).toBe("remote");
  });

  it("is Can't reach when the hub stops answering", () => {
    expect(hubLineStatus({ host: "fiestapi.local", hubReachable: false, deviceOnline: true })).toBe("unreachable");
  });

  it("is Can't reach when this device has no network", () => {
    expect(hubLineStatus({ host: "fiestapi.example.net", hubReachable: true, deviceOnline: false })).toBe(
      "unreachable",
    );
  });

  it("claims no state before the hub has answered or failed once", () => {
    expect(hubLineStatus({ host: "fiestapi.local", hubReachable: true, hubKnown: false, deviceOnline: true })).toBe(
      undefined,
    );
  });

  it("is Can't reach with no network even before the hub has answered", () => {
    expect(hubLineStatus({ host: "fiestapi.local", hubReachable: true, hubKnown: false, deviceOnline: false })).toBe(
      "unreachable",
    );
  });

  it("says nothing until it knows the host", () => {
    expect(hubLineStatus({ host: "", hubReachable: true, deviceOnline: true })).toBeUndefined();
  });
});
