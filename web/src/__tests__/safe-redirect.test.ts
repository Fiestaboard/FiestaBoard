import { afterEach, describe, expect, it } from "vitest";

import { safeRedirect } from "@/lib/safe-redirect";
describe("safeRedirect", () => {
  afterEach(() => {
    delete (window as unknown as { __reactRouterContext?: unknown }).__reactRouterContext;
  });
  it("preserves the activation code through login", () => {
    expect(safeRedirect("/activate?user_code=WDJB-MJHT")).toBe("/activate?user_code=WDJB-MJHT");
  });
  it.each([
    null,
    "",
    "https://attacker.invalid",
    "//attacker.invalid",
    "/\\attacker.invalid",
    "/%2fattacker.invalid",
    "/%252fattacker.invalid",
    "/%5cattacker.invalid",
    "/%0aevil",
    "/foo/../..//evil",
    " /settings",
    "/%ZZ",
  ])("rejects hostile redirects %s", (value) => {
    expect(safeRedirect(value)).toBe("/");
  });
  it("normalizes an ingress-prefixed target for basename-aware navigation", () => {
    (window as unknown as { __reactRouterContext: unknown }).__reactRouterContext = { basename: "/board/" };
    expect(safeRedirect("/board/activate?user_code=WDJB-MJHT")).toBe("/activate?user_code=WDJB-MJHT");
    expect(safeRedirect("/activate?user_code=WDJB-MJHT")).toBe("/activate?user_code=WDJB-MJHT");
  });
});

it("rejects an authority exposed by stripping the ingress prefix", () => {
  (window as unknown as { __reactRouterContext: unknown }).__reactRouterContext = { basename: "/board/" };
  expect(safeRedirect("/board//attacker.invalid")).toBe("/");
  expect(safeRedirect("/board/%2fattacker.invalid")).toBe("/");
});
