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

  it("reads an IPv6 loopback as local", () => {
    expect(hubHostKind("[::1]")).toBe("local");
  });
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

  it("says nothing until it knows the host", () => {
    expect(hubLineStatus({ host: "", hubReachable: true, deviceOnline: true })).toBeUndefined();
  });
});
