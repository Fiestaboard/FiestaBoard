import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { http, HttpResponse } from "msw";
import { server } from "./mocks/server";
import { ServiceStatus } from "@/components/service-status";
import { ServiceControls } from "@/components/service-controls";
import { ConfigDisplay } from "@/components/config-display";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";

const API_BASE = "/api";

// Test wrapper with providers
function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return (
    <QueryClientProvider client={queryClient}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          {children}
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}

describe("ServiceStatus", () => {
  it("shows running status when service is running", async () => {
    render(<ServiceStatus />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByLabelText("Display service is sending content to the board on a schedule.")).toBeInTheDocument();
    });
  });

  it("shows disconnected status on API error", async () => {
    server.use(
      http.get(`${API_BASE}/status`, () =>
        new HttpResponse(null, { status: 500 })
      )
    );

    render(<ServiceStatus />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByLabelText("Cannot reach the app. Check your network or that FiestaBoard is running.")).toBeInTheDocument();
    }, { timeout: 5000 });
  });

  it("shows stopped status when service is not running", async () => {
    server.use(
      http.get(`${API_BASE}/status`, () =>
        HttpResponse.json({ running: false, initialized: true, config_summary: {} })
      )
    );

    render(<ServiceStatus />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByLabelText("Display service is paused. Content is not being sent to the board.")).toBeInTheDocument();
    });
  });
});

describe("ServiceControls", () => {
  it("shows service status badge", async () => {
    render(<ServiceControls />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText(/Running|Stopped/)).toBeInTheDocument();
    });
  });

  it("shows Stopped badge when status.running is false", async () => {
    server.use(
      http.get(`${API_BASE}/status`, () =>
        HttpResponse.json({
          running: false,
          initialized: true,
          config_summary: {},
        })
      )
    );

    render(<ServiceControls />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText(/Stopped/)).toBeInTheDocument();
    });
  });
});

describe("ConfigDisplay", () => {
  it("shows enabled config items", async () => {
    render(<ConfigDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      // These are the short labels defined in config-display.tsx
      expect(screen.getByText("Date")).toBeInTheDocument();
      expect(screen.getByText("Weather")).toBeInTheDocument();
    });
  });

  it("shows on/off badges for config items", async () => {
    render(<ConfigDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      const onBadges = screen.getAllByText("On");
      const offBadges = screen.getAllByText("Off");
      expect(onBadges.length).toBeGreaterThan(0);
      expect(offBadges.length).toBeGreaterThan(0);
    });
  });
});

