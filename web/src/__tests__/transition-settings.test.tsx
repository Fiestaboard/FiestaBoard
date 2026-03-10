import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { TransitionSettings } from "@/components/settings/transition-settings";
import { http, HttpResponse } from "msw";
import { server } from "./mocks/server";
import { mockTransitionSettings } from "./mocks/handlers";

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

describe("TransitionSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders with current transition settings from API", async () => {
    render(<TransitionSettings />, { wrapper: TestWrapper });

    // Wait for data to load
    await waitFor(() => {
      expect(screen.getByText("Board Transitions")).toBeInTheDocument();
    });

    // Should display the strategy options
    expect(screen.getByText("Wave")).toBeInTheDocument();
    expect(screen.getByText("Drift")).toBeInTheDocument();
    expect(screen.getByText("Curtain")).toBeInTheDocument();
    expect(screen.getByText("Row")).toBeInTheDocument();
    expect(screen.getByText("Diagonal")).toBeInTheDocument();
    expect(screen.getByText("Random")).toBeInTheDocument();
    expect(screen.getByText("None")).toBeInTheDocument();
  });

  it("shows descriptions for each transition strategy", async () => {
    render(<TransitionSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Board Transitions")).toBeInTheDocument();
    });

    expect(screen.getByText(/column-by-column from left to right/)).toBeInTheDocument();
    expect(screen.getByText(/column-by-column from right to left/)).toBeInTheDocument();
    expect(screen.getByText(/both edges and meet in the center/)).toBeInTheDocument();
    expect(screen.getByText(/row-by-row from top to bottom/)).toBeInTheDocument();
    expect(screen.getByText(/diagonal wave/)).toBeInTheDocument();
    expect(screen.getByText(/random order/)).toBeInTheDocument();
    expect(screen.getByText(/updates all characters at once/)).toBeInTheDocument();
  });

  it("shows advanced options when a strategy is selected", async () => {
    render(<TransitionSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Board Transitions")).toBeInTheDocument();
    });

    // Mock returns strategy: "column", so advanced options should show
    await waitFor(() => {
      expect(screen.getByText("Advanced Options")).toBeInTheDocument();
      expect(screen.getByLabelText("Step Interval (ms)")).toBeInTheDocument();
      expect(screen.getByLabelText("Step Size")).toBeInTheDocument();
    });
  });

  it("hides advanced options when None is selected", async () => {
    // Override mock to return no strategy
    server.use(
      http.get(`${API_BASE}/settings/all`, () => {
        return HttpResponse.json({
          general: { timezone: "America/Los_Angeles" },
          silence_schedule: {},
          polling: { interval_seconds: 300 },
          transitions: { ...mockTransitionSettings, strategy: null },
          output: { target: "board", effective_target: "board", available_targets: [] },
          board: {
            board_type: "black",
            boards: [{ id: "default", name: "Flagship", device_type: "flagship", board_color: "black" }],
            devices: ["flagship"],
          },
          mqtt: { enabled: false, broker_host: "localhost", broker_port: 1883, username: "", password: "", external_url: "" },
          status: { running: true, config_summary: {} },
        });
      })
    );

    render(<TransitionSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Board Transitions")).toBeInTheDocument();
    });

    // Advanced options should not be visible when strategy is null
    expect(screen.queryByText("Advanced Options")).not.toBeInTheDocument();
  });

  it("displays info note about Local API requirement", async () => {
    render(<TransitionSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Board Transitions")).toBeInTheDocument();
    });

    expect(screen.getByText(/Local API/)).toBeInTheDocument();
    expect(screen.getByText(/Cloud API, transition settings will have no effect/)).toBeInTheDocument();
  });

  it("sends update when strategy is changed", async () => {
    let updatePayload: Record<string, unknown> | undefined;
    server.use(
      http.put(`${API_BASE}/settings/transitions`, async ({ request }) => {
        updatePayload = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          status: "success",
          settings: { strategy: "random", step_interval_ms: 500, step_size: 2 },
        });
      })
    );

    render(<TransitionSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Board Transitions")).toBeInTheDocument();
    });

    // Click on "Random"
    fireEvent.click(screen.getByText("Random"));

    // Wait for auto-save debounce
    await waitFor(
      () => {
        expect(updatePayload).toBeDefined();
      },
      { timeout: 3000 }
    );

    expect(updatePayload?.strategy).toBe("random");
  });
});
