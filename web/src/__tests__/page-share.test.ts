import { describe, expect, it } from "vitest";

import { encodePageShareString } from "@/lib/page-share";

function decode(share: string): unknown {
  const padded = share.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (share.length % 4)) % 4);
  const binary = atob(padded);
  return JSON.parse(new TextDecoder().decode(Uint8Array.from(binary, (c) => c.charCodeAt(0))));
}

describe("encodePageShareString (UX-1-4)", () => {
  it("wraps the page in the hub's v1 envelope, unpadded base64url", () => {
    const share = encodePageShareString({ name: "Good morning", template: ["HELLO"] });
    expect(share).not.toMatch(/[=+/]/);
    expect(decode(share)).toEqual({ v: 1, page: { name: "Good morning", template: ["HELLO"] } });
  });

  it("leaves out the server's identity fields, the demo marker and tags", () => {
    const share = encodePageShareString({
      id: "p1",
      revision: "r1",
      created_at: "x",
      updated_at: "y",
      edit_protocol: "e",
      document_protocol: "d",
      demo_plugin_id: "weather",
      tags: ["a"],
      name: "Kept",
    });
    expect(decode(share)).toEqual({ v: 1, page: { name: "Kept" } });
  });

  it("keeps characters outside Latin-1 intact", () => {
    expect(decode(encodePageShareString({ name: "Café ☕ 朝" }))).toEqual({ v: 1, page: { name: "Café ☕ 朝" } });
  });
});
