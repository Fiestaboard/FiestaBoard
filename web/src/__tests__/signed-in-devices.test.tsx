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
  expect(screen.getByRole("switch", { name: "TV sign-in" })).not.toBeChecked();
  expect(screen.getByText("Living room")).toBeInTheDocument();
  expect(screen.getByText(/existing devices keep access/i)).toBeInTheDocument();
});
it("revokes just the chosen device", async () => {
  render(<SignedInDevices />);
  const row = await screen.findByRole("listitem", { name: "Living room" });
  await userEvent.click(within(row).getByRole("button", { name: "Revoke Living room" }));
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

it("identifies the target device in each revoke button accessible name", async () => {
  render(<SignedInDevices />);
  await screen.findByText("This browser");
  expect(screen.getByRole("button", { name: "Revoke Desktop" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Revoke Living room" }));
  await waitFor(() => expect(screen.queryByText("Living room")).not.toBeInTheDocument());
  expect(revoked).toEqual(["tv"]);
  expect(screen.getByRole("button", { name: "Revoke Desktop" })).toBeInTheDocument();
});

it.each([
  [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/27.0 Safari/605.1.15",
    "Safari · macOS",
  ],
  ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36", "Chrome · Windows"],
  ["Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0", "Firefox · Linux"],
  [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36 Edg/130.0",
    "Edge · Windows",
  ],
  // Actual persisted shape: the server bounds raw User-Agent names to 100 characters.
  [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/27.",
    "Safari · macOS",
  ],
  [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/156.0.8078.4 S",
    "Browser · Linux",
  ],
  [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Sa",
    "Browser · Windows",
  ],
  ["Mozilla/5.0 (Unknown system) CustomBrowser/1.0", "Browser"],
])("presents browser metadata as a readable device name: %s", async (userAgent, label) => {
  sessions[0].device_name = userAgent;
  render(<SignedInDevices />);
  await screen.findByRole("listitem", { name: label });
  expect(screen.getByRole("button", { name: `Revoke ${label}` })).toBeInTheDocument();
  expect(screen.queryByText(userAgent)).not.toBeInTheDocument();
});

it("retries the initial device-list failure without changing any sign-ins", async () => {
  server.use(http.get("/api/auth/sessions", () => HttpResponse.json({ detail: "Unavailable" }, { status: 503 })));
  render(<SignedInDevices />);
  await screen.findByRole("alert");
  expect(screen.queryByText("Desktop")).not.toBeInTheDocument();
  server.use(http.get("/api/auth/sessions", () => HttpResponse.json({ sessions, current_session_id: "browser" })));
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  await screen.findByText("Desktop");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByText("Living room")).toBeInTheDocument();
  expect(revoked).toEqual([]);
  expect(bulk).toEqual([]);
});
