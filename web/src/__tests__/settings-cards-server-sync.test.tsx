import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import React from "react";
import { describe, expect, it } from "vitest";

import { AccessibilitySettings } from "@/components/settings/accessibility-settings";
import { InstanceNameCard } from "@/components/settings/instance-name";
import { TimeAndDateCard } from "@/components/settings/time-and-date";

import { server } from "./mocks/server";

const API_BASE = "/api";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

function withAllSettings(payload: Record<string, unknown>) {
  server.use(http.get(`${API_BASE}/settings/all`, () => HttpResponse.json(payload)));
}

/**
 * These cards used to mirror the `/settings/all` response into local form
 * state from a `useEffect`, which is the "cascading render" shape
 * `react-hooks/set-state-in-effect` flags (issue #1568). They now adjust that
 * state during render via `useDepsChanged`. The observable contract that must
 * survive the swap: the server value reaches the control, and a local edit is
 * not clobbered by a re-render that carries the same server data.
 */
describe("settings cards mirror server values without an effect", () => {
  describe("AccessibilitySettings", () => {
    it("shows the stored reduce-motion value once settings load", async () => {
      withAllSettings({ display: { reduce_motion: true } });
      render(<AccessibilitySettings />, { wrapper: TestWrapper });

      const toggle = await screen.findByRole("switch", { name: /reduce motion/i });
      await waitFor(() => expect(toggle).toBeChecked());
    });

    it("leaves the toggle off when the server has reduce motion disabled", async () => {
      withAllSettings({ display: { reduce_motion: false } });
      render(<AccessibilitySettings />, { wrapper: TestWrapper });

      const toggle = await screen.findByRole("switch", { name: /reduce motion/i });
      await waitFor(() => expect(toggle).not.toBeChecked());
    });
  });

  describe("InstanceNameCard", () => {
    it("shows the stored instance name once settings load", async () => {
      withAllSettings({ general: { instance_name: "Living Room" } });
      render(<InstanceNameCard />, { wrapper: TestWrapper });

      const input = await screen.findByLabelText("Instance Name");
      await waitFor(() => expect(input).toHaveValue("Living Room"));
    });

    it("keeps what the user typed when the same settings payload re-renders the card", async () => {
      // The refetch after a save re-delivers identical data; the sync must not
      // fire for it, or the field would snap back mid-edit.
      withAllSettings({ general: { instance_name: "Living Room" } });
      const user = userEvent.setup();
      const { rerender } = render(<InstanceNameCard />, { wrapper: TestWrapper });

      const input = await screen.findByLabelText("Instance Name");
      await waitFor(() => expect(input).toHaveValue("Living Room"));

      await user.clear(input);
      await user.type(input, "Kitchen");
      rerender(<InstanceNameCard />);

      expect(await screen.findByLabelText("Instance Name")).toHaveValue("Kitchen");
    });
  });

  describe("TimeAndDateCard", () => {
    it("shows the stored time format once settings load", async () => {
      withAllSettings({ general: { timezone: "America/New_York", time_format: "24h", date_format: "YYYY-MM-DD" } });
      render(<TimeAndDateCard />, { wrapper: TestWrapper });

      const trigger = await screen.findByLabelText("Time format");
      await waitFor(() => expect(trigger).toHaveTextContent("24-hour (14:30)"));
    });

    it("shows the stored date format once settings load", async () => {
      withAllSettings({ general: { timezone: "America/New_York", time_format: "24h", date_format: "YYYY-MM-DD" } });
      render(<TimeAndDateCard />, { wrapper: TestWrapper });

      const trigger = await screen.findByLabelText("Date format");
      await waitFor(() => expect(trigger).toHaveTextContent("YYYY-MM-DD"));
    });
  });
});
