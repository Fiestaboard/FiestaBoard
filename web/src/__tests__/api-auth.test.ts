/**
 * Focused tests for the auth-flavored api.ts helpers. The happy paths
 * are already exercised end-to-end by account-section.test.tsx and
 * login-page.test.tsx; this file covers the error / non-JSON / cookie
 * branches that those don't reach.
 */

import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";

import { server } from "./mocks/server";

describe("api auth helpers", () => {
  beforeEach(() => {
    // Each test installs its own handler — start clean.
  });

  describe("getAuthStatus", () => {
    it("returns the status payload on success", async () => {
      server.use(
        http.get("/api/auth/status", () =>
          HttpResponse.json({
            enabled: true,
            setup_required: false,
            authenticated: true,
            username: "alice",
            mode: "enabled",
            first_run: false,
          }),
        ),
      );
      const status = await api.getAuthStatus();
      expect(status.username).toBe("alice");
      expect(status.mode).toBe("enabled");
    });
  });

  describe("setAuthPreference", () => {
    it("posts the chosen preference", async () => {
      let body: { enabled?: boolean } | null = null;
      server.use(
        http.post("/api/auth/preference", async ({ request }) => {
          body = (await request.json()) as { enabled?: boolean };
          return HttpResponse.json({ status: "ok" });
        }),
      );
      await api.setAuthPreference(false);
      expect(body).toEqual({ enabled: false });
    });

    it("surfaces server detail on failure", async () => {
      server.use(
        http.post("/api/auth/preference", () =>
          HttpResponse.json({ detail: "A user already exists." }, { status: 409 }),
        ),
      );
      await expect(api.setAuthPreference(true)).rejects.toThrow(/already exists/);
    });

    it("falls back to a status-coded message when the body isn't JSON", async () => {
      server.use(http.post("/api/auth/preference", () => new HttpResponse("upstream exploded", { status: 502 })));
      await expect(api.setAuthPreference(true)).rejects.toThrow(/502/);
    });
  });

  describe("disableAuth", () => {
    it("sends the current password", async () => {
      let body: { current_password?: string } | null = null;
      server.use(
        http.post("/api/auth/disable", async ({ request }) => {
          body = (await request.json()) as { current_password?: string };
          return HttpResponse.json({ status: "ok" });
        }),
      );
      await api.disableAuth("hunter2");
      expect(body).toEqual({ current_password: "hunter2" });
    });

    it("surfaces server detail on wrong-password", async () => {
      server.use(
        http.post("/api/auth/disable", () => HttpResponse.json({ detail: "Password is incorrect" }, { status: 401 })),
      );
      await expect(api.disableAuth("wrong")).rejects.toThrow(/incorrect/);
    });

    it("falls back to a status-coded message on non-JSON failure", async () => {
      server.use(http.post("/api/auth/disable", () => new HttpResponse("nope", { status: 500 })));
      await expect(api.disableAuth("hunter2")).rejects.toThrow(/500/);
    });
  });

  describe("changePassword", () => {
    it("surfaces server detail on failure", async () => {
      server.use(
        http.post("/api/auth/change-password", () =>
          HttpResponse.json({ detail: "Current password is incorrect" }, { status: 401 }),
        ),
      );
      await expect(api.changePassword("wrong", "newsecret")).rejects.toThrow(/incorrect/);
    });

    it("falls back to a status-coded message when body isn't JSON", async () => {
      server.use(http.post("/api/auth/change-password", () => new HttpResponse("nope", { status: 500 })));
      await expect(api.changePassword("p", "newsecret")).rejects.toThrow(/500/);
    });
  });

  describe("changeUsername", () => {
    it("surfaces server detail on failure", async () => {
      server.use(
        http.post("/api/auth/change-username", () =>
          HttpResponse.json({ detail: "Password is incorrect" }, { status: 401 }),
        ),
      );
      await expect(api.changeUsername("wrong", "owner")).rejects.toThrow(/incorrect/);
    });

    it("falls back to a status-coded message when body isn't JSON", async () => {
      server.use(http.post("/api/auth/change-username", () => new HttpResponse("nope", { status: 500 })));
      await expect(api.changeUsername("p", "owner")).rejects.toThrow(/500/);
    });
  });

  describe("logout", () => {
    it("issues a POST and resolves on 200", async () => {
      let called = false;
      server.use(
        http.post("/api/auth/logout", () => {
          called = true;
          return HttpResponse.json({ status: "ok" });
        }),
      );
      await api.logout();
      expect(called).toBe(true);
    });
  });

  describe("fetchApi redirect-to-login", () => {
    // The shared fetchApi() helper auto-redirects to /login on 401
    // and on 409 setup_required. Exercise both branches via a
    // representative GET so the redirect helper itself is covered.

    let originalLocation: Location;
    let assignMock: ReturnType<typeof vi.fn>;

    beforeEach(() => {
      assignMock = vi.fn();
      originalLocation = window.location;
      // Re-define window.location with our mock assign, mimicking a
      // dashboard route (not /login, so the redirect actually fires).
      Object.defineProperty(window, "location", {
        configurable: true,
        value: {
          ...originalLocation,
          pathname: "/",
          search: "",
          assign: assignMock,
        },
      });
    });

    afterEach(() => {
      Object.defineProperty(window, "location", {
        configurable: true,
        value: originalLocation,
      });
    });

    it("redirects to /login on 401", async () => {
      server.use(http.get("/api/status", () => HttpResponse.json({ detail: "Not authenticated" }, { status: 401 })));
      await expect(api.getStatus()).rejects.toThrow();
      expect(assignMock).toHaveBeenCalledWith(expect.stringMatching(/^\/login\?redirect=/));
    });

    it("redirects to /login on 409 with setup_required", async () => {
      server.use(
        http.get("/api/status", () =>
          HttpResponse.json({ detail: "Setup required", setup_required: true, first_run: true }, { status: 409 }),
        ),
      );
      await expect(api.getStatus()).rejects.toThrow();
      // The 409→redirect path peeks the body asynchronously, so wait a
      // microtask for the clone().json() promise to resolve.
      await new Promise((r) => setTimeout(r, 0));
      expect(assignMock).toHaveBeenCalledWith(expect.stringMatching(/^\/login\?redirect=/));
    });

    it("does NOT redirect on 409 without setup_required", async () => {
      server.use(http.get("/api/status", () => HttpResponse.json({ detail: "Some other conflict" }, { status: 409 })));
      await expect(api.getStatus()).rejects.toThrow();
      await new Promise((r) => setTimeout(r, 0));
      expect(assignMock).not.toHaveBeenCalled();
    });
  });
});
