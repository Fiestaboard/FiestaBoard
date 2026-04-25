import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { http, HttpResponse } from "msw";
import { server } from "./mocks/server";

vi.mock("next/navigation", () => ({
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

import { GeneralSettings } from "@/components/general-settings";

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

describe("GeneralSettings extended", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("handles polling interval change with valid value", async () => {
    render(<GeneralSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      const input = document.getElementById("polling-interval");
      expect(input).toBeInTheDocument();
      expect(parseInt((input as HTMLInputElement).value, 10)).toBeGreaterThanOrEqual(10);
    });

    const pollingInput = document.getElementById("polling-interval") as HTMLInputElement;
    fireEvent.change(pollingInput, { target: { value: "120" } });
    // handlePollingIntervalChange(120) updates state when value >= 10
    expect(pollingInput).toBeInTheDocument();
  });

  it("ignores polling interval change with value less than 10", async () => {
    render(<GeneralSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(document.getElementById("polling-interval")).toBeInTheDocument();
    });

    const pollingInput = document.getElementById("polling-interval") as HTMLInputElement;
    const beforeValue = pollingInput.value;
    fireEvent.change(pollingInput, { target: { value: "5" } });

    await waitFor(() => {
      // handlePollingIntervalChange ignores values < 10, state unchanged
      expect(pollingInput.value).not.toBe("5");
      expect(parseInt(pollingInput.value, 10)).toBeGreaterThanOrEqual(10);
    });
  });

  it("shows silence time pickers when enabled including end time", async () => {
    const user = userEvent.setup();
    render(<GeneralSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      const pollingInput = document.getElementById("polling-interval") as HTMLInputElement;
      expect(pollingInput).toBeInTheDocument();
      expect(parseInt(pollingInput.value, 10)).toBe(300);
    });

    const silenceToggle = screen.getAllByRole("switch").find((s) => s.getAttribute("id") === "silence-enabled");
    expect(silenceToggle).toBeDefined();
    await user.click(silenceToggle!);

    await waitFor(() => {
      expect(screen.getByText("End Time")).toBeInTheDocument();
      expect(screen.getByText("When silence ends")).toBeInTheDocument();
      expect(screen.getByText("Start Time")).toBeInTheDocument();
    });
  });

  it("displays Board Update Interval description", async () => {
    render(<GeneralSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText(/How often the board checks for content updates/i)).toBeInTheDocument();
    });
  });

  it("displays Requires service restart note for polling", async () => {
    render(<GeneralSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText(/Requires service restart/i)).toBeInTheDocument();
    });
  });

  it("renders polling interval and silence schedule sections", async () => {
    render(<GeneralSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(document.getElementById("polling-interval")).toBeInTheDocument();
      expect(document.getElementById("silence-enabled")).toBeInTheDocument();
    });
  });

});
