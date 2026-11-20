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
it("identifies this browser and keeps device management visible when enrollment is off", async () => {
  render(<SignedInDevices />);
  await screen.findByText("This browser");
  expect(screen.getByRole("switch", { name: "Device sign-in" })).not.toBeChecked();
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
  ["Sign out other devices…", false],
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
  expect(screen.queryByRole("button", { name: "Revoke Desktop" })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Revoke Living room" }));
  await waitFor(() => expect(screen.queryByText("Living room")).not.toBeInTheDocument());
  expect(revoked).toEqual(["tv"]);
  expect(screen.queryByRole("button", { name: "Revoke Desktop" })).not.toBeInTheDocument();
});

it.each([
  [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/27.0 Safari/605.1.15",
    "Safari on macOS",
  ],
  ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36", "Chrome on Windows"],
  ["Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0", "Firefox on Linux"],
  [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36 Edg/130.0",
    "Edge on Windows",
  ],
  // Actual persisted shape: the server bounds raw User-Agent names to 100 characters.
  [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/27.",
    "Safari on macOS",
  ],
  [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/156.0.8078.4 S",
    "Browser on Linux",
  ],
  [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Sa",
    "Browser on Windows",
  ],
  // Automation's Chrome (the bug bash's own browser) is still Chrome.
  [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/156.0.8078.4 Safari/537.36",
    "Chrome on Linux",
  ],
  ["Mozilla/5.0 (Unknown system) CustomBrowser/1.0", "Browser"],
])("presents browser metadata as a readable device name: %s", async (userAgent, label) => {
  sessions[0].device_name = userAgent;
  render(<SignedInDevices />);
  await screen.findByRole("listitem", { name: label });
  expect(screen.queryByRole("button", { name: `Revoke ${label}` })).not.toBeInTheDocument();
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

it("identifies a paired phone with its QR connection", async () => {
  sessions.push({
    ...sessions[1],
    id: "phone",
    device_name: "Pixel",
    kind: "mobile",
    client_id: "fiestaboard-android",
    method: "pairing",
  });
  render(<SignedInDevices />);
  const row = await screen.findByRole("listitem", { name: "Pixel" });
  expect(within(row).getByText(/Connected with a QR code/)).toBeInTheDocument();
  expect(within(row).queryByText(/Password/)).not.toBeInTheDocument();
});

it("offers phone pairing and groups session kinds without a sign-out on this browser", async () => {
  sessions.push({ ...sessions[1], id: "phone", kind: "mobile", device_name: "Pixel", method: "pairing" });
  render(<SignedInDevices />);
  await screen.findByText("Desktop");
  expect(screen.getByRole("button", { name: "Connect a phone" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Phones" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Browsers" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Revoke Desktop" })).not.toBeInTheDocument();
});

it("confirms a phone cascade by default and lets the browser keep its TVs", async () => {
  sessions.push({ ...sessions[1], id: "phone", kind: "mobile", device_name: "Pixel", method: "pairing" });
  sessions[1].approved_by = { session_id: "phone", kind: "mobile", label: "Pixel", signed_in: true };
  let cascade: string | null = null;
  server.use(
    http.delete("/api/auth/sessions/:id", ({ request }) => {
      cascade = new URL(request.url).searchParams.get("include_approved");
      sessions = sessions.filter((row) => row.id !== "phone");
      return HttpResponse.json({ status: "ok", also_signed_out: [] });
    }),
  );
  render(<SignedInDevices />);
  const row = await screen.findByRole("listitem", { name: "Pixel" });
  await userEvent.click(within(row).getByRole("button", { name: "Revoke Pixel" }));
  const dialog = await screen.findByRole("alertdialog");
  const checkbox = within(dialog).getByRole("checkbox");
  expect(checkbox).toBeChecked();
  expect(within(dialog).getByText("Living room")).toBeInTheDocument();
  await userEvent.click(checkbox);
  await userEvent.click(within(dialog).getByRole("button", { name: "Sign out phone" }));
  await waitFor(() => expect(cascade).toBe("false"));
  expect(screen.getByText("Living room")).toBeInTheDocument();
});

it("shows an app-only QR, polls the claim, and removes the consumed code", async () => {
  let claimed = false;
  server.use(
    http.post("/api/auth/pairing", () =>
      HttpResponse.json({
        pairing_id: "offer",
        qr_payload: "fiestaboard://pair#v=1&hub=http%3A%2F%2Ffiestapi.local&code=test_only",
        hub: "http://fiestapi.local",
        expires_in: 300,
        hub_addresses: [{ url: "http://fiestapi.local", kind: "mdns" }],
      }),
    ),
    http.get("/api/auth/pairing/offer", () =>
      HttpResponse.json(
        claimed ? { state: "claimed", device_name: "Pixel", session_id: "phone" } : { state: "pending" },
      ),
    ),
    http.delete("/api/auth/pairing", () => HttpResponse.json({ status: "ok" })),
  );
  render(<SignedInDevices />);
  await userEvent.click(await screen.findByRole("button", { name: "Connect a phone" }));
  expect(await screen.findByRole("img", { name: "Scan with the FiestaBoard app" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /fiestaboard:\/\// })).not.toBeInTheDocument();
  claimed = true;
  await screen.findByText("Pixel is connected", {}, { timeout: 5000 });
  expect(screen.queryByRole("img", { name: "Scan with the FiestaBoard app" })).not.toBeInTheDocument();
});

it("refuses a loopback hub in a pairing payload", async () => {
  server.use(
    http.post("/api/auth/pairing", () =>
      HttpResponse.json({
        pairing_id: "bad",
        qr_payload: "fiestaboard://pair#v=1&hub=http%3A%2F%2Flocalhost%3A4420&code=test_only",
        hub: "http://localhost:4420",
        expires_in: 300,
        hub_addresses: [],
      }),
    ),
    http.delete("/api/auth/pairing", () => HttpResponse.json({ status: "ok" })),
  );
  render(<SignedInDevices />);
  await userEvent.click(await screen.findByRole("button", { name: "Connect a phone" }));
  await screen.findByText(/Couldn’t make a safe QR code/);
  expect(screen.queryByRole("img", { name: "Scan with the FiestaBoard app" })).not.toBeInTheDocument();
});

it("resolves last-shown panel names without confusing them with last-connected time", async () => {
  sessions[1].last_shown_at = "2026-10-17T10:00:00Z";
  sessions[1].shown_panels = [{ panel_id: "panel-id", last_shown_at: "2026-10-17T10:00:00Z" }];
  server.use(
    http.get("/api/panels", () => HttpResponse.json({ panels: [{ id: "panel-id", name: "Kitchen panel" }], total: 1 })),
  );
  render(<SignedInDevices />);
  const row = await screen.findByRole("listitem", { name: "Living room" });
  await within(row).findByText(/Last shown: Kitchen panel/);
  expect(within(row).getByText(/Last connected/)).toBeInTheDocument();
  expect(within(row).queryByText(/panel-id/)).not.toBeInTheDocument();
});

it("names the remaining TV after a partial phone sign-out and keeps the same cascade retry available", async () => {
  sessions.push({ ...sessions[1], id: "phone", kind: "mobile", device_name: "Pixel", method: "pairing" });
  sessions[1].approved_by = { session_id: "phone", kind: "mobile", label: "Pixel", signed_in: true };
  let attempts = 0;
  server.use(
    http.delete("/api/auth/sessions/:id", () => {
      attempts++;
      sessions = sessions.filter((row) => row.id !== "phone");
      if (attempts === 1) return HttpResponse.json({ detail: "Storage unavailable" }, { status: 503 });
      sessions = sessions.filter((row) => row.id !== "tv");
      return HttpResponse.json({ status: "ok", also_signed_out: ["tv"] });
    }),
  );
  render(<SignedInDevices />);
  await userEvent.click(await screen.findByRole("button", { name: "Revoke Pixel" }));
  await userEvent.click(screen.getByRole("button", { name: "Sign out phone and 1 TVs" }));
  await screen.findByText(/Living room didn’t respond/);
  expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Sign out phone and 1 TVs" }));
  await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
  expect(screen.queryByText("Living room")).not.toBeInTheDocument();
  expect(attempts).toBe(2);
});

describe("07e Account › Signed-in devices (`322:31855` / `321:9076`, BB-C-24)", () => {
  // Local wall-clock times, so the expectations hold in any TZ.
  const NOW = new Date(2026, 10, 20, 18, 0);
  const at = (day: number, hour: number, minute: number) => new Date(2026, 10, day, hour, minute).toISOString();
  const MAC_CHROME =
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";
  const IPAD_SAFARI =
    "Mozilla/5.0 (iPad; CPU OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1";

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"], now: NOW });
    sessions = [
      {
        id: "browser",
        device_name: MAC_CHROME,
        kind: "browser",
        method: "password",
        created_at: at(2, 9, 0),
        last_active_at: NOW.toISOString(),
      },
      {
        id: "ipad",
        device_name: IPAD_SAFARI,
        kind: "browser",
        method: "password",
        created_at: at(19, 8, 0),
        last_active_at: at(19, 21, 12),
      },
      {
        id: "tv",
        device_name: "Living room",
        kind: "tv",
        client_id: "fiestaboard-tvos",
        method: "device_code",
        created_at: at(5, 9, 0),
        last_active_at: at(20, 17, 39),
      },
      {
        id: "script",
        device_name: "Legacy client (may retain your password)",
        kind: "legacy",
        method: "password",
        created_at: at(20, 7, 15),
        last_active_at: at(20, 7, 15),
      },
    ].map((row) => ({ ...row, expires_at: "2027-10-18T00:00:00Z" }));
  });
  afterEach(() => vi.useRealTimers());

  it("names browsers as '<browser> on <system>' and says how and when they signed in", async () => {
    render(<SignedInDevices />);
    const mac = await screen.findByRole("listitem", { name: "Chrome on macOS" });
    expect(within(mac).getByText("Signed in with a password · Nov 2")).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "Safari on iOS" })).toBeInTheDocument();
  });

  it("reads last-connected times relative to now", async () => {
    render(<SignedInDevices />);
    const mac = await screen.findByRole("listitem", { name: "Chrome on macOS" });
    expect(within(mac).getByText("Last connected just now")).toBeInTheDocument();
    const ipad = screen.getByRole("listitem", { name: "Safari on iOS" });
    expect(within(ipad).getByText(/^Last connected yesterday, 9:12\sPM$/)).toBeInTheDocument();
    const tv = screen.getByRole("listitem", { name: "Living room" });
    expect(within(tv).getByText(/^Last connected 5:39\sPM$/)).toBeInTheDocument();
    expect(screen.queryByText(/11\/20\/2026/)).not.toBeInTheDocument();
  });

  it("does not call a password-signed-in app or script an older TV app", async () => {
    render(<SignedInDevices />);
    const row = await screen.findByRole("listitem", { name: "App signed in with a password" });
    expect(screen.queryByRole("heading", { name: /older TV app/i })).not.toBeInTheDocument();
    const group = screen.getByRole("heading", { name: "Apps & older TVs · Signed in with a password" });
    expect(group.parentElement).toContainElement(row);
    expect(screen.queryByText("Legacy client (may retain your password)")).not.toBeInTheDocument();
    expect(within(row).getByText(/may keep your password/i)).toBeInTheDocument();
  });
});
