/**
 * BB-FC-13: Account › Signed-in devices against 07e.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SignedInDevices } from "@/components/settings/signed-in-devices";

import { server } from "./mocks/server";
const router = { replace: vi.fn() };
vi.mock("@/hooks/use-router", () => ({ useRouter: () => router }));
let revoked: string[];
let bulk: boolean[];
let sessions: Record<string, unknown>[];
beforeEach(() => {
  revoked = [];
  bulk = [];
  router.replace.mockReset();
  sessions = [
    { id: "browser", device_name: "Desktop", kind: "browser", method: "password" },
    { id: "tv", device_name: "Living room", kind: "tv", client_id: "fiestaboard-tvos", method: "device_code" },
  ].map((row) => ({
    ...row,
    created_at: "2026-10-18T00:00:00Z",
    last_active_at: "2026-10-18T00:00:00Z",
    expires_at: "2027-10-18T00:00:00Z",
  }));
  server.use(
    http.get("/api/panels", () => HttpResponse.json({ panels: [], total: 0 })),
    http.get("/api/auth/sessions", () => HttpResponse.json({ sessions, current_session_id: "browser" })),
    http.get("/api/auth/sessions/context", () => HttpResponse.json({ csrf_token: "nonce", expires_in: 600 })),
    http.get("/api/auth/device/settings", () => HttpResponse.json({ enabled: false })),
    http.put("/api/auth/device/settings", () => HttpResponse.json({ enabled: true })),
    http.delete("/api/auth/sessions/:id", ({ params }) => {
      revoked.push(String(params.id));
      sessions = sessions.filter((row) => row.id !== params.id);
      return HttpResponse.json({ status: "ok" });
    }),
    http.post("/api/auth/sessions/revoke", async ({ request }) => {
      bulk.push(((await request.json()) as { include_current: boolean }).include_current);
      return HttpResponse.json({ status: "ok" });
    }),
  );
});

/*
 * BB-FC-13: 07e `321:9076` draws the "Signed-in devices" heading row with
 * two buttons on its right, outline "Sign out other devices…" then primary
 * "Connect a phone", and a legend chip with a clock and a monitor icon.
 */
it("puts Sign out other devices… then Connect a phone on the heading row", async () => {
  render(<SignedInDevices />);
  await screen.findByText("This browser");
  const heading = screen.getByRole("heading", { level: 3, name: "Signed-in devices" });
  const row = heading.closest("[data-slot=signed-in-devices-head]") as HTMLElement;
  expect(row).not.toBeNull();
  const buttons = within(row).getAllByRole("button");
  expect(buttons.map((button) => button.textContent?.trim())).toEqual(["Sign out other devices…", "Connect a phone"]);
});

it("draws the legend with a clock and a monitor icon", async () => {
  render(<SignedInDevices />);
  await screen.findByText("This browser");
  const legend = document.querySelector("[data-slot=signed-in-devices-legend]")!;
  expect(legend.querySelectorAll("svg")).toHaveLength(2);
  expect(legend.textContent).toContain("Last connected = when it last talked to the hub");
  expect(legend.textContent).toContain("Last shown = the panel a TV last displayed");
});
