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
      // ServiceStatus uses aria-label for the status indicator
      expect(screen.getByLabelText("Service status: Running")).toBeInTheDocument();
    });
  });
});

describe("ServiceControls", () => {
  it("shows dev mode switch", async () => {
    render(<ServiceControls />, { wrapper: TestWrapper });

    await waitFor(() => {
      // There may be multiple switches (dev mode + auto-refresh), get by id
      expect(screen.getByRole("switch", { name: /dev mode/i })).toBeInTheDocument();
    });
  });

  it("shows service status badge", async () => {
    render(<ServiceControls />, { wrapper: TestWrapper });

    await waitFor(() => {
      // Should show either "Running" or "Stopped" badge
      expect(screen.getByText(/Running|Stopped/)).toBeInTheDocument();
    });
  });

  it("shows dev mode description", async () => {
    render(<ServiceControls />, { wrapper: TestWrapper });

    await waitFor(() => {
      // Should show description about preview/live mode
      expect(screen.getByText(/Preview mode|Live mode/)).toBeInTheDocument();
    });
  });

  it("calls toast.success with API message when dev mode toggle succeeds", async () => {
    const toastSpy = vi.spyOn((await import("sonner")).toast, "success");
    const user = userEvent.setup();

    render(<ServiceControls />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("switch", { name: /dev mode/i })).toBeInTheDocument();
    });

    const switchEl = screen.getByRole("switch", { name: /dev mode/i });
    await user.click(switchEl);

    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith(expect.stringMatching(/Dev mode (enabled|disabled)/));
    });

    toastSpy.mockRestore();
  });

  it("uses fallback message when API returns success without message", async () => {
    server.use(
      http.post(`${API_BASE}/dev-mode`, async ({ request }) => {
        const body = await request.json() as { dev_mode: boolean };
        return HttpResponse.json({
          status: "success",
          dev_mode: body.dev_mode,
          // No message - triggers fallback
        });
      })
    );

    const toastSpy = vi.spyOn((await import("sonner")).toast, "success");
    const user = userEvent.setup();

    render(<ServiceControls />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("switch", { name: /dev mode/i })).toBeInTheDocument();
    });

    const switchEl = screen.getByRole("switch", { name: /dev mode/i });
    await user.click(switchEl);

    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith(expect.stringMatching(/Dev mode (enabled|disabled)/));
    });

    toastSpy.mockRestore();
  });

  it("calls toast.error when dev mode toggle fails", async () => {
    server.use(
      http.post(`${API_BASE}/dev-mode`, () =>
        new HttpResponse(null, { status: 500 })
      )
    );

    const toastSpy = vi.spyOn((await import("sonner")).toast, "error");
    const user = userEvent.setup();

    render(<ServiceControls />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("switch", { name: /dev mode/i })).toBeInTheDocument();
    });

    const switchEl = screen.getByRole("switch", { name: /dev mode/i });
    await user.click(switchEl);

    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith("Failed to toggle dev mode");
    });

    toastSpy.mockRestore();
  });

  it("shows Stopped badge when status.running is false", async () => {
    server.use(
      http.get(`${API_BASE}/status`, () =>
        HttpResponse.json({
          running: false,
          initialized: true,
          config_summary: { dev_mode: false },
        })
      )
    );

    render(<ServiceControls />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText(/Stopped/)).toBeInTheDocument();
    });
  });

  it("handles missing config_summary with dev_mode fallback", async () => {
    server.use(
      http.get(`${API_BASE}/status`, () =>
        HttpResponse.json({
          running: true,
          initialized: true,
          // config_summary omitted - dev_mode should fallback to false
        })
      )
    );

    render(<ServiceControls />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText(/Live mode/)).toBeInTheDocument();
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

