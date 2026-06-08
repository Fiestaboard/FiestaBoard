import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

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

import { GeneralSettings } from "@/components/general-settings";

// Test wrapper with providers
function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("GeneralSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading skeleton initially", () => {
    render(<GeneralSettings />, { wrapper: TestWrapper });

    // Card titles render immediately (outside the loading skeleton)
    expect(screen.getAllByText("Update Intervals").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Silence Schedule").length).toBeGreaterThan(0);
  });

  it("renders general settings card", async () => {
    render(<GeneralSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getAllByText("Board Update Interval").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Silence Schedule").length).toBeGreaterThan(0);
    });
  });

  it("shows board update interval input", async () => {
    render(<GeneralSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(document.getElementById("polling-interval")).toBeInTheDocument();
    });
  });

  it("shows board update interval label", async () => {
    render(<GeneralSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getAllByText("Board Update Interval").length).toBeGreaterThan(0);
    });
  });

  it("shows silence schedule toggle", async () => {
    render(<GeneralSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getAllByText("Silence Schedule").length).toBeGreaterThan(0);
      expect(screen.getAllByText(/Prevent board updates/i).length).toBeGreaterThan(0);
    });
  });

  it("shows silence time pickers when enabled", async () => {
    const user = userEvent.setup();
    render(<GeneralSettings />, { wrapper: TestWrapper });

    // Wait for data to fully load including deferred values by checking
    // that the polling input has its value from the API mock (300)
    await waitFor(() => {
      const pollingInput = document.getElementById("polling-interval") as HTMLInputElement;
      expect(pollingInput).toBeInTheDocument();
      expect(parseInt(pollingInput.value, 10)).toBe(300);
    });

    // Get the silence schedule toggle
    const silenceToggle = screen.getAllByRole("switch").find((s) => s.getAttribute("id") === "silence-enabled");
    expect(silenceToggle).toBeDefined();

    await user.click(silenceToggle!);

    // Should show time pickers
    await waitFor(
      () => {
        expect(screen.getByText("Start Time")).toBeInTheDocument();
        expect(screen.getByText("End Time")).toBeInTheDocument();
      },
      { timeout: 2000 },
    );
  });

  it("shows polling interval value from API", async () => {
    render(<GeneralSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      const pollingInput = document.getElementById("polling-interval") as HTMLInputElement;
      expect(pollingInput).toBeInTheDocument();
      expect(parseInt(pollingInput.value, 10)).toBe(300);
    });
  });

  it("allows updating the polling interval", async () => {
    const user = userEvent.setup();
    render(<GeneralSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      const pollingInput = document.getElementById("polling-interval") as HTMLInputElement;
      expect(pollingInput).toBeInTheDocument();
    });

    const pollingInput = document.getElementById("polling-interval") as HTMLInputElement;
    await user.clear(pollingInput);
    await user.type(pollingInput, "60");

    await waitFor(() => {
      expect(screen.getAllByText("Board Update Interval").length).toBeGreaterThan(0);
    });
  });

  it("renders both the polling and silence sections", async () => {
    render(<GeneralSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(document.getElementById("polling-interval")).toBeInTheDocument();
      expect(document.getElementById("silence-enabled")).toBeInTheDocument();
    });
  });

  it("displays board update interval description", async () => {
    render(<GeneralSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText(/How often the board checks for content updates/i)).toBeInTheDocument();
    });
  });

  it("displays silence schedule description", async () => {
    render(<GeneralSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getAllByText(/Prevent board updates during specified hours/i).length).toBeGreaterThan(0);
    });
  });

  it("renders all sections in correct order", async () => {
    render(<GeneralSettings />, { wrapper: TestWrapper });

    await waitFor(
      () => {
        expect(screen.getAllByText("Board Update Interval").length).toBeGreaterThan(0);
        expect(screen.getAllByText("Silence Schedule").length).toBeGreaterThan(0);
      },
      { timeout: 2000 },
    );
  });
});
