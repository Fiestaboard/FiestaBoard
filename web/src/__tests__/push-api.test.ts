import { afterEach, describe, expect, it, vi } from "vitest";

import { pushApi } from "@/lib/api/push";

afterEach(() => {
  vi.unstubAllGlobals();
  Reflect.deleteProperty(window, "__reactRouterContext");
});

describe("browser push API", () => {
  it("prefixes ingress, uses cookies and fresh CSRF on every mutation, never a bearer", async () => {
    Object.assign(window, { __reactRouterContext: { basename: "/ingress/test/" } });
    let nonce = 0;
    const fetcher = vi.fn(async (url: string, options?: RequestInit) => {
      expect(options).toMatchObject({ credentials: "same-origin", cache: "no-store", redirect: "error" });
      if (url.endsWith("/context")) return Response.json({ csrf_token: `nonce-${++nonce}` });
      expect(options!.headers).toMatchObject({ "X-CSRF-Token": `nonce-${nonce}` });
      expect(options!.headers).not.toHaveProperty("Authorization");
      return Response.json({ user_enabled: true });
    });
    vi.stubGlobal("fetch", fetcher);
    await pushApi.setPreference(true);
    await pushApi.unsubscribe();
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
      "/ingress/test/api/auth/sessions/context",
      "/ingress/test/api/push/preferences",
      "/ingress/test/api/auth/sessions/context",
      "/ingress/test/api/push/subscription",
    ]);
    expect(fetcher.mock.calls[1][1]).toMatchObject({ method: "PUT", body: '{"enabled":true}' });
    expect(fetcher.mock.calls[3][1]).toMatchObject({ method: "DELETE" });
  });

  it("keeps test delivery counts instead of reducing an HTTP 200 to success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        Response.json(
          url.endsWith("context") ? { csrf_token: "nonce" } : { sent: 0, failed: 0, skipped: 1, expired: 0 },
        ),
      ),
    );
    expect(await pushApi.sendTest()).toEqual({ sent: 0, failed: 0, skipped: 1, expired: 0 });
  });

  it("carries status codes without exposing server body text", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ detail: "secret endpoint" }, { status: 503 })),
    );
    await expect(pushApi.getStatus()).rejects.toMatchObject({ status: 503, message: "Push request failed" });
  });
});
