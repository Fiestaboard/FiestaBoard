// Branch coverage for UpdateIntervals onBlur + mutation onSuccess paths.
// The existing general-settings tests cover onChange and board-read blur,
// but not the polling-interval blur or the requires_restart branch.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { ThemeProvider } from "@/hooks/use-theme";
import { act } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { server } from "./mocks/server";

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => "/settings",
}));

import { UpdateIntervals } from "@/components/settings/update-intervals";

const API_BASE = "/api";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="light">
        {children}
      </ThemeProvider>
    </QueryClientProvider>
  );
}

describe("UpdateIntervals — mutation branches", () => {
  beforeEach(() => {
    server.resetHandlers();
  });

  it("onBlur for polling-interval triggers updatePollingSettings with requires_restart=true branch", async () => {
    let capturedBody: unknown;
    server.use(
      http.put(`${API_BASE}/settings/polling`, async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json({
          status: "success",
          settings: { interval_seconds: 60 },
          requires_restart: true,
        });
      }),
    );

    render(<UpdateIntervals />, { wrapper: TestWrapper });

    // Wait for the deferred React Query data to populate state
    await waitFor(() => {
      const el = document.getElementById("polling-interval") as HTMLInputElement;
      expect(el).toBeInTheDocument();
      expect(parseInt(el.value, 10)).toBe(300);
    });
    await act(async () => {});

    const input = document.getElementById("polling-interval") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "60" } });
    await waitFor(() => expect(parseInt(input.value, 10)).toBe(60));
    await act(async () => {});
    fireEvent.blur(input);

    await waitFor(() => {
      expect(capturedBody).toMatchObject({ interval_seconds: 60 });
    });
  });

  it("onBlur for polling-interval triggers updatePollingSettings with requires_restart=false branch", async () => {
    let capturedBody: unknown;
    server.use(
      http.put(`${API_BASE}/settings/polling`, async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json({
          status: "success",
          settings: { interval_seconds: 45 },
          requires_restart: false,
        });
      }),
    );

    render(<UpdateIntervals />, { wrapper: TestWrapper });

    await waitFor(() => {
      const el = document.getElementById("polling-interval") as HTMLInputElement;
      expect(el).toBeInTheDocument();
      expect(parseInt(el.value, 10)).toBe(300);
    });
    await act(async () => {});

    const input = document.getElementById("polling-interval") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "45" } });
    await waitFor(() => expect(parseInt(input.value, 10)).toBe(45));
    await act(async () => {});
    fireEvent.blur(input);

    await waitFor(() => {
      expect(capturedBody).toMatchObject({ interval_seconds: 45 });
    });
  });

  it("ignores polling-interval onChange when value is below the minimum", async () => {
    render(<UpdateIntervals />, { wrapper: TestWrapper });

    await waitFor(() => {
      const el = document.getElementById("polling-interval") as HTMLInputElement;
      expect(parseInt(el.value, 10)).toBe(300);
    });
    await act(async () => {});

    const input = document.getElementById("polling-interval") as HTMLInputElement;
    // value < 10 should be rejected by handlePollingIntervalChange
    fireEvent.change(input, { target: { value: "5" } });

    // State did not update — value remains 300
    expect(parseInt(input.value, 10)).toBe(300);
  });
});
