import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, expect, it, vi } from "vitest";

import Activate from "../../app/routes/activate";
import { server } from "./mocks/server";
const router = { replace: vi.fn(), push: vi.fn() };
const params = new URLSearchParams();
vi.mock("@/hooks/use-router", () => ({ useRouter: () => router, useSearchParams: () => params }));
let approved = 0;
let inspected = "";
const status = {
  enabled: true,
  authenticated: true,
  setup_required: false,
  auth_kind: "browser",
  tv_sign_in: { supported: true, enabled: true, protocol_version: 1 },
};
beforeEach(() => {
  params.delete("user_code");
  router.replace.mockReset();
  approved = 0;
  inspected = "";
  server.use(
    http.get("/api/auth/status", () => HttpResponse.json(status)),
    http.get("/api/auth/sessions/context", () => HttpResponse.json({ csrf_token: "nonce", expires_in: 600 })),
    http.post("/api/auth/device/inspect", async ({ request }) => {
      inspected = ((await request.json()) as { user_code: string }).user_code;
      return HttpResponse.json({
        user_code: "WDJB-MJHT",
        device_name: "Living room TV",
        client_id: "fiestaboard-tvos",
        app_version: "1.2",
        expires_in: 600,
        scope: "tv_panels",
      });
    }),
    http.post("/api/auth/device/approve", () => {
      approved++;
      return HttpResponse.json({ status: "ok" });
    }),
    http.post("/api/auth/device/deny", () => HttpResponse.json({ status: "ok" })),
  );
});
it("scanning displays consent without approving; only Allow grants access", async () => {
  params.set("user_code", "WDJB-MJHT");
  render(<Activate />);
  await screen.findByText("Living room TV");
  expect(approved).toBe(0);
  expect(screen.getByText(/view and control panels/i)).toBeInTheDocument();
  expect(document.querySelector('meta[name="referrer"]')).toHaveAttribute("content", "no-referrer");
  await userEvent.click(screen.getByRole("button", { name: "Allow this TV" }));
  await screen.findByText(/TV approved/i);
  expect(approved).toBe(1);
});
it("preserves the scanned code through anonymous login", async () => {
  server.use(http.get("/api/auth/status", () => HttpResponse.json({ ...status, authenticated: false })));
  params.set("user_code", "WDJB-MJHT");
  render(<Activate />);
  await waitFor(() =>
    expect(router.replace).toHaveBeenCalledWith("/login?redirect=%2Factivate%3Fuser_code%3DWDJB-MJHT"),
  );
  expect(approved).toBe(0);
});
it("normalizes manual codes and requires explicit consent", async () => {
  render(<Activate />);
  await userEvent.type(await screen.findByLabelText("TV code"), "wdjb mjht");
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByText("Living room TV");
  expect(inspected).toBe("WDJBMJHT");
  expect(approved).toBe(0);
  await userEvent.click(screen.getByRole("button", { name: "Deny" }));
  await screen.findByText(/request was denied/i);
  expect(approved).toBe(0);
});
it.each(["expired_token", "access_denied", "invalid_grant"])("cannot approve unusable code %s", async (error) => {
  server.use(
    http.post("/api/auth/device/inspect", () =>
      HttpResponse.json({ error, detail: "Code unavailable" }, { status: 400 }),
    ),
  );
  params.set("user_code", "WDJB-MJHT");
  render(<Activate />);
  await screen.findByRole("alert");
  expect(screen.queryByRole("button", { name: "Allow this TV" })).not.toBeInTheDocument();
});
it("explains disabled enrollment", async () => {
  server.use(
    http.get("/api/auth/status", () =>
      HttpResponse.json({ ...status, tv_sign_in: { ...status.tv_sign_in, enabled: false } }),
    ),
  );
  render(<Activate />);
  await screen.findByText(/TV sign-in is disabled/i);
  expect(approved).toBe(0);
});
