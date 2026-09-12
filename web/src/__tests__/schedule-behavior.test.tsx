import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { ScheduleBehavior } from "@/components/settings/schedule-behavior";

import { server } from "./mocks/server";

const API_BASE = "/api";

const toastMock = vi.hoisted(() => ({
  success: vi.fn(),
  info: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: toastMock,
  Toaster: () => null,
}));

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

/** Serve /settings/all with a chosen defer_on_reenable value. */
function withDeferSetting(defer: boolean) {
  server.use(
    http.get(`${API_BASE}/settings/all`, () =>
      HttpResponse.json({
        general: { timezone: "UTC", refresh_interval_seconds: 300, output_target: "board" },
        schedule: { defer_on_reenable: defer },
        status: { running: true },
      }),
    ),
  );
}

describe("ScheduleBehavior", () => {
  it("renders the switch off when the server has the setting off", async () => {
    withDeferSetting(false);

    render(<ScheduleBehavior />, { wrapper: TestWrapper });

    const toggle = await screen.findByRole("switch");
    await waitFor(() => expect(toggle).toHaveAttribute("aria-checked", "false"));
  });

  it("reflects the stored setting when it is already on", async () => {
    withDeferSetting(true);

    render(<ScheduleBehavior />, { wrapper: TestWrapper });

    const toggle = await screen.findByRole("switch");
    await waitFor(() => expect(toggle).toHaveAttribute("aria-checked", "true"));
  });

  it("persists the new value when toggled on", async () => {
    withDeferSetting(false);
    let sent: { defer_on_reenable: boolean } | null = null;
    server.use(
      http.put(`${API_BASE}/schedules/settings`, async ({ request }) => {
        sent = (await request.json()) as { defer_on_reenable: boolean };
        return HttpResponse.json({ status: "success", defer_on_reenable: sent.defer_on_reenable });
      }),
    );

    render(<ScheduleBehavior />, { wrapper: TestWrapper });
    await userEvent.click(await screen.findByRole("switch"));

    await waitFor(() => expect(sent).toEqual({ defer_on_reenable: true }));
  });

  it("surfaces a save failure instead of silently keeping the new position", async () => {
    withDeferSetting(false);
    server.use(
      http.put(`${API_BASE}/schedules/settings`, () => HttpResponse.json({ detail: "nope" }, { status: 500 })),
    );

    render(<ScheduleBehavior />, { wrapper: TestWrapper });
    await userEvent.click(await screen.findByRole("switch"));

    await waitFor(() => expect(toastMock.error).toHaveBeenCalled());
  });
});
