import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchApi } from "@/lib/api/core";
import { classifyInstallSuccess, emitApiSuccess, onApiSuccess } from "@/lib/api/success-events";

import { server } from "./mocks/server";

describe("API success events", () => {
  const stops: Array<() => void> = [];
  afterEach(() => {
    stops.splice(0).forEach((stop) => stop());
  });

  it("tells listeners the method and path of a successful fetchApi call, without the query", async () => {
    server.use(http.post("*/api/v1/pages", () => HttpResponse.json({ id: "p1" })));
    const seen = vi.fn();
    stops.push(onApiSuccess(seen));
    await fetchApi("/v1/pages?draft=1", { method: "post", body: "{}" });
    expect(seen).toHaveBeenCalledWith({ method: "POST", path: "/v1/pages" });
  });

  it("says nothing when the call fails", async () => {
    server.use(http.post("*/api/v1/pages", () => HttpResponse.json({ detail: "no" }, { status: 400 })));
    const seen = vi.fn();
    stops.push(onApiSuccess(seen));
    await expect(fetchApi("/v1/pages", { method: "POST", body: "{}" })).rejects.toThrow();
    expect(seen).not.toHaveBeenCalled();
  });

  it("keeps the API call's result when a listener throws", () => {
    stops.push(
      onApiSuccess(() => {
        throw new Error("listener bug");
      }),
    );
    const after = vi.fn();
    stops.push(onApiSuccess(after));
    expect(() => emitApiSuccess(undefined, "/status")).not.toThrow();
    expect(after).toHaveBeenCalledWith({ method: "GET", path: "/status" });
  });

  it("stops telling a listener once it unsubscribes", () => {
    const seen = vi.fn();
    onApiSuccess(seen)();
    emitApiSuccess("GET", "/status");
    expect(seen).not.toHaveBeenCalled();
  });
});

describe("classifyInstallSuccess", () => {
  it.each([
    ["POST", "/v1/boards/b1/message", "send"],
    ["PUT", "/settings/active-page", "send"],
    ["POST", "/send-welcome-message", "send"],
    ["POST", "/v1/pages", "save"],
    ["PUT", "/v1/pages/abc", "save"],
    ["GET", "/v1/pages", null],
    ["DELETE", "/v1/pages/abc", null],
    ["GET", "/board/current-message", null],
    ["POST", "/v1/boards/b1/message/extra", null],
  ] as const)("%s %s → %s", (method, path, expected) => {
    expect(classifyInstallSuccess({ method, path })).toBe(expected);
  });
});
