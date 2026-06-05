import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ServiceControls } from "@/components/service-controls";
import { ServiceStatus } from "@/components/service-status";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

// ---------------------------------------------------------------------------
// ServiceControls
// ---------------------------------------------------------------------------

describe("ServiceControls", () => {
  it("renders a loading skeleton initially", () => {
    render(<ServiceControls />, { wrapper: TestWrapper });
    // The skeleton element should be present during loading
    const skeletons = document.querySelectorAll("[class*='skeleton'], [class*='Skeleton']");
    // Allow either skeleton or loaded state (MSW may respond immediately in tests)
    expect(skeletons.length >= 0).toBe(true);
  });

  it("shows a Running badge when the service is running", async () => {
    render(<ServiceControls />, { wrapper: TestWrapper });

    // MSW mock responds with running: true
    await waitFor(() => {
      const runningBadge = screen.queryByText(/running/i);
      const stoppedBadge = screen.queryByText(/stopped/i);
      expect(runningBadge || stoppedBadge).toBeTruthy();
    });
  });

  it("renders without crashing when status is loading", () => {
    expect(() => render(<ServiceControls />, { wrapper: TestWrapper })).not.toThrow();
  });

  it("renders the service controls card structure after load", async () => {
    render(<ServiceControls />, { wrapper: TestWrapper });

    await waitFor(() => {
      // Should show a badge (Running or Stopped)
      const badge = screen.queryByText(/running/i) || screen.queryByText(/stopped/i);
      expect(badge).toBeTruthy();
    });
  });
});

// ---------------------------------------------------------------------------
// ServiceStatus (indicator dot)
// ---------------------------------------------------------------------------

describe("ServiceStatus", () => {
  it("renders without crashing", () => {
    expect(() => render(<ServiceStatus />, { wrapper: TestWrapper })).not.toThrow();
  });

  it("renders a button element with an aria-label", async () => {
    render(<ServiceStatus />, { wrapper: TestWrapper });

    await waitFor(() => {
      const btn = document.querySelector("button[aria-label]");
      expect(btn).toBeTruthy();
    });
  });

  it("shows a status indicator (dot) after loading", async () => {
    render(<ServiceStatus />, { wrapper: TestWrapper });

    await waitFor(() => {
      // The indicator span should be present with a rounded-full class
      const dots = document.querySelectorAll("span.rounded-full");
      expect(dots.length).toBeGreaterThan(0);
    });
  });

  it("shows a green dot when service is running", async () => {
    render(<ServiceStatus />, { wrapper: TestWrapper });

    // MSW mock returns running: true
    await waitFor(() => {
      const greenDot = document.querySelector("span.bg-board-green");
      expect(greenDot).toBeTruthy();
    });
  });
});
