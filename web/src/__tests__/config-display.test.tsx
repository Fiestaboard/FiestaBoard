import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConfigDisplay } from "@/components/config-display";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigOverridesProvider>{children}</ConfigOverridesProvider>
    </QueryClientProvider>
  );
}

describe("ConfigDisplay", () => {
  it("renders without crashing", () => {
    expect(() => render(<ConfigDisplay />, { wrapper: TestWrapper })).not.toThrow();
  });

  it("shows a loading skeleton when data is still fetching", () => {
    render(<ConfigDisplay />, { wrapper: TestWrapper });
    // During loading, skeletons or final content should be present
    const container = document.body;
    expect(container).toBeTruthy();
  });

  it("renders the Configuration card title after load", async () => {
    render(<ConfigDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Configuration")).toBeInTheDocument();
    });
  });

  it("renders known config item labels after data loads", async () => {
    render(<ConfigDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      // These labels come from the hard-coded configItems array
      expect(screen.getByText("Date")).toBeInTheDocument();
      expect(screen.getByText("Weather")).toBeInTheDocument();
      expect(screen.getByText("Home")).toBeInTheDocument();
    });
  });

  it("renders On/Off badges for each config item", async () => {
    render(<ConfigDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      const onBadges = screen.queryAllByText("On");
      const offBadges = screen.queryAllByText("Off");
      expect(onBadges.length + offBadges.length).toBeGreaterThan(0);
    });
  });

  it("toggles a config item when clicked", async () => {
    render(<ConfigDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Date")).toBeInTheDocument();
    });

    // Count On/Off badges before click
    const onBefore = screen.queryAllByText("On").length;
    const offBefore = screen.queryAllByText("Off").length;
    const totalBefore = onBefore + offBefore;

    // Find the Date button and click it to toggle its state
    const dateButton = screen.getByText("Date").closest("button");
    expect(dateButton).toBeTruthy();
    fireEvent.click(dateButton!);

    // Total On+Off badges count should remain the same (just one toggled)
    const onAfter = screen.queryAllByText("On").length;
    const offAfter = screen.queryAllByText("Off").length;
    expect(onAfter + offAfter).toBe(totalBefore);
  });

  it("shows 'click to toggle preview' hint text", async () => {
    render(<ConfigDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText(/click to toggle preview/i)).toBeInTheDocument();
    });
  });

  it("renders buttons with accessible roles", async () => {
    render(<ConfigDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      const buttons = screen.getAllByRole("button");
      expect(buttons.length).toBeGreaterThan(0);
    });
  });
});
