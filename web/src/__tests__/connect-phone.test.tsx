import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, expect, it, vi } from "vitest";

import { ConnectPhone } from "@/components/settings/connect-phone";
import { sessionsApi } from "@/lib/api/sessions";

import { server } from "./mocks/server";

const offer = {
  pairing_id: "offer",
  qr_payload: "fiestaboard://pair#v=1&hub=http%3A%2F%2Ffiestapi.local&code=test_only",
  hub: "http://fiestapi.local",
  expires_in: 300,
  hub_addresses: [{ url: "http://fiestapi.local", kind: "mdns" }],
};
beforeEach(async () => {
  server.use(
    http.get("/api/auth/sessions/context", () => HttpResponse.json({ csrf_token: "nonce", expires_in: 600 })),
    http.post("/api/auth/pairing", () => HttpResponse.json(offer)),
    http.get("/api/auth/pairing/offer", () => HttpResponse.json({ state: "pending" })),
    http.delete("/api/auth/pairing", () => HttpResponse.json({ status: "ok" })),
  );
  await sessionsApi.cancelPairing();
});
it("removes the QR on expiration and renews it only after an explicit request", async () => {
  let creations = 0;
  server.use(
    http.post("/api/auth/pairing", () => {
      creations++;
      return HttpResponse.json({ ...offer, expires_in: creations === 1 ? 1 : 300 });
    }),
  );
  render(<ConnectPhone open onClose={vi.fn()} onChanged={vi.fn()} />);
  await screen.findByRole("img", { name: "Scan with the FiestaBoard app" });
  await screen.findByText("This code expired");
  expect(screen.queryByRole("img", { name: "Scan with the FiestaBoard app" })).not.toBeInTheDocument();
  expect(creations).toBe(1);
  await userEvent.click(screen.getByRole("button", { name: "Make a new code" }));
  await screen.findByRole("img", { name: "Scan with the FiestaBoard app" });
  expect(creations).toBe(2);
});
it("cancels an in-flight creation before a reopened dialog makes its code", async () => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const events: string[] = [];
  let first = true;
  server.use(
    http.post("/api/auth/pairing", async () => {
      if (first) {
        first = false;
        events.push("creating");
        await gate;
      }
      events.push("created");
      return HttpResponse.json(offer);
    }),
    http.delete("/api/auth/pairing", () => {
      events.push("cancelled");
      return HttpResponse.json({ status: "ok" });
    }),
  );
  const view = render(<ConnectPhone open onClose={vi.fn()} onChanged={vi.fn()} />);
  await waitFor(() => expect(events).toEqual(["creating"]));
  view.unmount();
  render(<ConnectPhone open onClose={vi.fn()} onChanged={vi.fn()} />);
  release();
  await screen.findByRole("img", { name: "Scan with the FiestaBoard app" });
  expect(events).toEqual(["creating", "created", "cancelled", "created"]);
});
it("retries a failed creation without rendering a stale QR", async () => {
  server.use(http.post("/api/auth/pairing", () => HttpResponse.json({ detail: "Unavailable" }, { status: 503 })));
  render(<ConnectPhone open onClose={vi.fn()} onChanged={vi.fn()} />);
  await screen.findByText(/Couldn’t make a safe QR code/);
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  server.use(http.post("/api/auth/pairing", () => HttpResponse.json(offer)));
  await userEvent.click(screen.getByRole("button", { name: "Make a new code" }));
  await screen.findByRole("img", { name: "Scan with the FiestaBoard app" });
});
it("signs out the newly connected phone and refreshes the device list", async () => {
  const revoked: string[] = [];
  const changed = vi.fn();
  const close = vi.fn();
  server.use(
    http.get("/api/auth/pairing/offer", () =>
      HttpResponse.json({ state: "claimed", session_id: "phone", device_name: "Pixel" }),
    ),
    http.delete("/api/auth/sessions/:id", ({ params }) => {
      revoked.push(String(params.id));
      return HttpResponse.json({ status: "ok" });
    }),
  );
  render(<ConnectPhone open onClose={close} onChanged={changed} />);
  await screen.findByText("Pixel is connected");
  await userEvent.click(screen.getByRole("button", { name: "Sign it out" }));
  await waitFor(() => expect(close).toHaveBeenCalledOnce());
  expect(revoked).toEqual(["phone"]);
  expect(changed).toHaveBeenCalledTimes(2);
});
it.each([
  "http://127.0.0.2",
  "http://[::1]",
  "http://[::ffff:127.0.0.1]",
  "http://0.0.0.0",
  "http://example.localhost",
])("never draws a QR for %s", async (hub) => {
  server.use(
    http.post("/api/auth/pairing", () =>
      HttpResponse.json({
        ...offer,
        hub,
        qr_payload: `fiestaboard://pair#v=1&hub=${encodeURIComponent(hub)}&code=test_only`,
      }),
    ),
  );
  render(<ConnectPhone open onClose={vi.fn()} onChanged={vi.fn()} />);
  await screen.findByText(/Couldn’t make a safe QR code/);
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});

it("checks server truth after the local countdown reaches zero so a last-second claim is not missed", async () => {
  server.use(
    http.post("/api/auth/pairing", () => HttpResponse.json({ ...offer, expires_in: 1 })),
    http.get("/api/auth/pairing/offer", () =>
      HttpResponse.json({ state: "claimed", session_id: "phone", device_name: "Just connected" }),
    ),
  );
  render(<ConnectPhone open onClose={vi.fn()} onChanged={vi.fn()} />);
  await screen.findByRole("img", { name: "Scan with the FiestaBoard app" });
  await screen.findByText("This code expired");
  expect(screen.queryByText("Nothing was connected.")).not.toBeInTheDocument();
  await screen.findByText("Just connected is connected");
});

it.each([
  [403, "feature_disabled", "Device sign-in is disabled. Enable device sign-in in Settings → Account."],
  [401, "unauthorized", "Sign in again to continue."],
  [429, "rate_limited", "Too many attempts. Wait a moment and try again."],
] as const)("explains an actionable pairing refusal (%s)", async (status, error, message) => {
  server.use(http.post("/api/auth/pairing", () => HttpResponse.json({ error }, { status })));
  render(<ConnectPhone open onClose={vi.fn()} onChanged={vi.fn()} />);
  await screen.findByText(message);
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});
