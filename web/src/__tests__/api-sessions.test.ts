import { http, HttpResponse } from "msw";
import { expect, it, vi } from "vitest";

import { sessionsApi } from "@/lib/api/sessions";

import { server } from "./mocks/server";
it("gets a fresh session-bound nonce and sends it with every mutation without caching", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch");
  let contexts = 0;
  const requests: { csrf: string | null; body: unknown }[] = [];
  server.use(
    http.get("/api/auth/sessions/context", ({ request }) => {
      contexts++;
      return HttpResponse.json({ csrf_token: `nonce-${contexts}`, expires_in: 600 });
    }),
    http.post("/api/auth/device/approve", async ({ request }) => {
      requests.push({ csrf: request.headers.get("X-CSRF-Token"), body: await request.json() });
      return HttpResponse.json({ status: "ok" });
    }),
  );
  await sessionsApi.approveDevice("WDJB-MJHT");
  await sessionsApi.approveDevice("BCDF-GHJK");
  expect(fetchSpy.mock.calls.every(([, options]) => options?.cache === "no-store")).toBe(true);
  fetchSpy.mockRestore();
  expect(requests).toEqual([
    { csrf: "nonce-1", body: { user_code: "WDJB-MJHT" } },
    { csrf: "nonce-2", body: { user_code: "BCDF-GHJK" } },
  ]);
});
it("preserves stable protocol errors for the activation UI", async () => {
  server.use(
    http.get("/api/auth/sessions", () =>
      HttpResponse.json({ error: "invalid_session", detail: "Sign in again" }, { status: 401 }),
    ),
  );
  await expect(sessionsApi.listSessions()).rejects.toMatchObject({ code: "invalid_session", status: 401 });
});
