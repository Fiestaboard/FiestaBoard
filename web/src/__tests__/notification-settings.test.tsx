import "fake-indexeddb/auto";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { NotificationSettings } from "@/components/settings/notification-settings";
import { pushApi, type PushStatus } from "@/lib/api/push";
import * as browser from "@/lib/pwa/push";
import { clearAccountDataOnDevice } from "@/lib/pwa/sign-out";

import { server } from "./mocks/server";

vi.mock("@/lib/pwa/push", async (original) => ({
  ...(await original<typeof import("@/lib/pwa/push")>()),
  getPushAvailability: vi.fn(() => "supported"),
  readBrowserPush: vi.fn(async () => ({ permission: "default", subscribed: false })),
  enableBrowserPush: vi.fn(),
  disableBrowserPush: vi.fn(),
}));

let status: PushStatus;
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(browser.getPushAvailability).mockReturnValue("supported");
  vi.mocked(browser.readBrowserPush).mockResolvedValue({ permission: "default", subscribed: false });
  status = {
    public_key: "key",
    user_enabled: false,
    device_enabled: false,
    subscribed: false,
    expiration_time: null,
    event_sources: [],
    test_available: false,
  };
  server.use(
    http.get("/api/push/status", () => HttpResponse.json(status)),
    http.get("/api/auth/sessions/context", () => HttpResponse.json({ csrf_token: "nonce" })),
    http.put("/api/push/preferences", async ({ request }) => {
      status.user_enabled = ((await request.json()) as { enabled: boolean }).enabled;
      return HttpResponse.json(status);
    }),
  );
});

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });
}

function show(client = makeClient()) {
  return render(
    <QueryClientProvider client={client}>
      <NotificationSettings />
    </QueryClientProvider>,
  );
}

async function enrolled() {
  status = { ...status, user_enabled: true, device_enabled: true, subscribed: true, test_available: true };
  vi.mocked(browser.readBrowserPush).mockResolvedValue({ permission: "granted", subscribed: true });
  show();
  await waitFor(() => expect(screen.getByRole("button", { name: "Send a test" })).toBeEnabled());
}

describe("notification settings", () => {
  it("refreshes external browser permission changes on return with production focus defaults", async () => {
    status.user_enabled = true;
    vi.mocked(browser.readBrowserPush).mockResolvedValue({ permission: "denied", subscribed: false });
    show();
    const device = await screen.findByRole("switch", { name: "Enable on this browser" });
    expect(device).toBeDisabled();
    vi.mocked(browser.readBrowserPush).mockResolvedValue({ permission: "granted", subscribed: false });
    fireEvent.focus(window);
    await waitFor(() => expect(device).toBeEnabled());
    expect(screen.queryByText("Notifications blocked by the browser")).not.toBeInTheDocument();
    vi.mocked(browser.readBrowserPush).mockResolvedValue({ permission: "denied", subscribed: false });
    fireEvent(document, new Event("visibilitychange"));
    await waitFor(() => expect(device).toBeDisabled());
    expect(browser.enableBrowserPush).not.toHaveBeenCalled();
  });

  it("does not reuse the old session's consent after rapid sign-out and sign-in", async () => {
    const client = makeClient();
    status = { ...status, user_enabled: true, device_enabled: true, subscribed: true };
    const first = show(client);
    expect(await screen.findByRole("switch", { name: "Allow notifications for my account" })).toBeChecked();
    first.unmount();
    await clearAccountDataOnDevice(client);
    status = { ...status, user_enabled: false, device_enabled: false, subscribed: false };
    show(client);
    expect(await screen.findByRole("switch", { name: "Allow notifications for my account" })).not.toBeChecked();
    expect(screen.getByRole("switch", { name: "Enable on this browser" })).not.toBeChecked();
  });

  it("does not restore consent when a pending save finishes after sign-out", async () => {
    const client = makeClient();
    let finish!: (value: PushStatus) => void;
    const save = vi.spyOn(pushApi, "setPreference").mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    try {
      const first = show(client);
      await userEvent.click(await screen.findByRole("switch", { name: "Allow notifications for my account" }));
      expect(save).toHaveBeenCalledOnce();
      first.unmount();
      await clearAccountDataOnDevice(client);
      await act(async () => {
        finish({ ...status, user_enabled: true });
      });
      expect(client.getQueryData(["push-status"])).toBeUndefined();
    } finally {
      save.mockRestore();
    }
  });

  it("discards in-flight enrollment reads at sign-out", async () => {
    const client = makeClient();
    let finish!: (value: PushStatus) => void;
    const result = client
      .fetchQuery({
        queryKey: ["push-status"],
        queryFn: () =>
          new Promise<PushStatus>((resolve) => {
            finish = resolve;
          }),
      })
      .catch(() => undefined);
    client.setQueryData(["browser-push"], { permission: "granted", subscribed: true });
    await clearAccountDataOnDevice(client);
    await act(async () => {
      finish(status);
      await result;
    });
    expect(client.getQueryData(["push-status"])).toBeUndefined();
    expect(client.getQueryData(["browser-push"])).toBeUndefined();
  });

  it("still explains HTTPS when no browser session exists", async () => {
    vi.mocked(browser.getPushAvailability).mockReturnValue("insecure");
    server.use(http.get("/api/push/status", () => HttpResponse.json({}, { status: 401 })));
    show();
    expect(await screen.findByText("Sign in to enable notifications")).toBeVisible();
    expect(screen.getByText("Requires HTTPS")).toBeVisible();
  });
  it("never prompts on load and keeps account consent separate from browser enrollment", async () => {
    const user = userEvent.setup();
    show();
    const account = await screen.findByRole("switch", { name: "Allow notifications for my account" });
    expect(account).not.toBeChecked();
    expect(screen.getByRole("switch", { name: "Enable on this browser" })).toBeDisabled();
    await user.click(account);
    await waitFor(() => expect(account).toBeChecked());
    expect(browser.enableBrowserPush).not.toHaveBeenCalled();
    expect(screen.getByRole("switch", { name: "Enable on this browser" })).toBeEnabled();
  });

  it("enables only after an explicit browser activation and refreshes browser state", async () => {
    status.user_enabled = true;
    vi.mocked(browser.enableBrowserPush).mockImplementation(async () => {
      vi.mocked(browser.readBrowserPush).mockResolvedValue({ permission: "granted", subscribed: true });
      return { ...status, device_enabled: true, subscribed: true, test_available: true };
    });
    const user = userEvent.setup();
    show();
    await user.click(await screen.findByRole("switch", { name: "Enable on this browser" }));
    await waitFor(() => expect(screen.getByRole("switch", { name: "Enable on this browser" })).toBeChecked());
    expect(browser.enableBrowserPush).toHaveBeenCalledWith("key");
    expect(screen.getByText("Allowed by this browser")).toBeVisible();
  });

  it("keeps all unsupported event categories off and explains why", async () => {
    await enrolled();
    expect(screen.getByText(/Automatic alerts are not available yet/)).toBeVisible();
    for (const name of [
      "A display goes offline",
      "An override ends",
      "Update available",
      "Silence Schedule held a message",
    ]) {
      expect(screen.getByRole("switch", { name })).toBeDisabled();
      expect(screen.getByRole("switch", { name })).not.toBeChecked();
    }
  });

  it("reports a skipped HTTP 200 as not sent", async () => {
    server.use(http.post("/api/push/test", () => HttpResponse.json({ sent: 0, failed: 0, skipped: 1, expired: 0 })));
    await enrolled();
    await userEvent.click(screen.getByRole("button", { name: "Send a test" }));
    expect(await screen.findByText("The test was not sent. Try again later.")).toBeVisible();
    expect(screen.queryByText(/push service accepted/)).not.toBeInTheDocument();
  });

  it.each([
    ["failed", { sent: 0, failed: 1, skipped: 0, expired: 0 }],
    ["failed with skips", { sent: 0, failed: 2, skipped: 1, expired: 0 }],
  ])("reports %s HTTP 200 counts as a failed test", async (_name, result) => {
    server.use(http.post("/api/push/test", () => HttpResponse.json(result)));
    await enrolled();
    await userEvent.click(screen.getByRole("button", { name: "Send a test" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Sending the test notification failed. Try again later.",
    );
    expect(screen.queryByText("The test was not sent. Try again later.")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Send a test" })).toBeEnabled());
    expect(screen.getByRole("switch", { name: "Enable on this browser" })).toBeChecked();
  });

  it.each([
    ["empty counts", { sent: 0, failed: 0, skipped: 0, expired: 0 }, "The test was not sent. Try again later."],
    [
      "accepted counts take precedence",
      { sent: 1, failed: 1, skipped: 1, expired: 1 },
      "The push service accepted the test. Check this browser for the notification.",
    ],
    [
      "expired counts take precedence over failure",
      { sent: 0, failed: 1, skipped: 1, expired: 1 },
      "This subscription expired. Enable this browser again.",
    ],
  ])("preserves feedback for %s", async (_name, result, message) => {
    server.use(http.post("/api/push/test", () => HttpResponse.json(result)));
    await enrolled();
    await userEvent.click(screen.getByRole("button", { name: "Send a test" }));
    expect(await screen.findByRole("status")).toHaveTextContent(message);
  });

  it("refreshes enrollment after an expired test subscription", async () => {
    server.use(
      http.post("/api/push/test", () => {
        status = { ...status, device_enabled: false, subscribed: false, test_available: false };
        return HttpResponse.json({ sent: 0, failed: 0, skipped: 0, expired: 1 });
      }),
    );
    await enrolled();
    await userEvent.click(screen.getByRole("button", { name: "Send a test" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "This subscription expired. Enable this browser again.",
    );
    await waitFor(() => expect(screen.getByRole("switch", { name: "Enable on this browser" })).not.toBeChecked());
    expect(screen.getByRole("button", { name: "Send a test" })).toBeDisabled();
  });

  it.each([
    [429, "Please wait a minute before sending another test."],
    [503, "The push service could not accept the test. Try again later."],
  ])("preserves HTTP %s test feedback", async (code, message) => {
    server.use(http.post("/api/push/test", () => HttpResponse.json({}, { status: code })));
    await enrolled();
    await userEvent.click(screen.getByRole("button", { name: "Send a test" }));
    expect(await screen.findByRole("status")).toHaveTextContent(message);
    await waitFor(() => expect(screen.getByRole("button", { name: "Send a test" })).toBeEnabled());
  });

  it("describes accepted tests as provider acceptance, not guaranteed display", async () => {
    server.use(http.post("/api/push/test", () => HttpResponse.json({ sent: 1, failed: 0, skipped: 0, expired: 0 })));
    await enrolled();
    await userEvent.click(screen.getByRole("button", { name: "Send a test" }));
    expect(await screen.findByText(/The push service accepted the test/)).toBeVisible();
  });

  it.each([
    ["insecure", "Requires HTTPS"],
    ["embedded", "Open your hub directly"],
    ["install", "Add FiestaBoard to your Home Screen"],
    ["unsupported", "Notifications unavailable"],
  ] as const)("explains %s without offering permission", async (availability, title) => {
    vi.mocked(browser.getPushAvailability).mockReturnValue(availability);
    status.user_enabled = true;
    show();
    expect(await screen.findByText(title)).toBeVisible();
    expect(await screen.findByRole("switch", { name: "Enable on this browser" })).toBeDisabled();
    expect(browser.enableBrowserPush).not.toHaveBeenCalled();
  });

  it("explains denied permission and lets an enrolled browser be disabled", async () => {
    status = { ...status, user_enabled: true, device_enabled: true, subscribed: true };
    vi.mocked(browser.readBrowserPush).mockResolvedValue({ permission: "denied", subscribed: true });
    vi.mocked(browser.disableBrowserPush).mockResolvedValue({ ...status, device_enabled: false, subscribed: false });
    show();
    expect(await screen.findByText("Notifications blocked by the browser")).toBeVisible();
    await userEvent.click(screen.getByRole("switch", { name: "Enable on this browser" }));
    await waitFor(() => expect(browser.disableBrowserPush).toHaveBeenCalledOnce());
  });

  it("requires a browser session when the hub has authentication disabled", async () => {
    server.use(http.get("/api/push/status", () => HttpResponse.json({}, { status: 401 })));
    show();
    expect(await screen.findByText("Sign in to enable notifications")).toBeVisible();
    expect(screen.queryByRole("switch", { name: "Allow notifications for my account" })).not.toBeInTheDocument();
  });

  it("reports failures without losing the previous account state", async () => {
    server.use(http.put("/api/push/preferences", () => HttpResponse.json({}, { status: 503 })));
    show();
    await userEvent.click(await screen.findByRole("switch", { name: "Allow notifications for my account" }));
    expect(
      await screen.findByText("Could not update notifications. Check your connection and try again."),
    ).toBeVisible();
    expect(screen.getByRole("switch", { name: "Allow notifications for my account" })).not.toBeChecked();
  });
});
