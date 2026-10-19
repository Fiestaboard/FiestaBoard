import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, expect, it, vi } from "vitest";

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
it("identifies this browser and keeps device management visible when enrollment is off", async () => {
  render(<SignedInDevices />);
  await screen.findByText("This browser");
  expect(screen.getByRole("switch", { name: "TV sign-in (Beta)" })).not.toBeChecked();
  expect(screen.getByText("Living room")).toBeInTheDocument();
  expect(screen.getByText(/existing devices keep access/i)).toBeInTheDocument();
});
it("revokes just the chosen device", async () => {
  render(<SignedInDevices />);
  const row = await screen.findByRole("listitem", { name: "Living room" });
  await userEvent.click(within(row).getByRole("button", { name: "Revoke" }));
  await waitFor(() => expect(screen.queryByText("Living room")).not.toBeInTheDocument());
  expect(revoked).toEqual(["tv"]);
  expect(screen.getByText("Desktop")).toBeInTheDocument();
});
it.each([
  ["Sign out other devices", false],
  ["Sign out everywhere", true],
] as const)("confirms %s", async (label, includeCurrent) => {
  render(<SignedInDevices />);
  await screen.findByText("Desktop");
  await userEvent.click(screen.getByRole("button", { name: label }));
  expect(bulk).toEqual([]);
  const dialog = await screen.findByRole("alertdialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Confirm" }));
  await waitFor(() => expect(bulk).toEqual([includeCurrent]));
  if (includeCurrent) expect(router.replace).toHaveBeenCalledWith("/login");
});
