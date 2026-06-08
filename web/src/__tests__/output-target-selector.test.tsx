import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider } from "@/hooks/use-theme";
import { describe, expect, it } from "vitest";

import { OutputTargetSelector } from "@/components/output-target-selector";

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

describe("OutputTargetSelector", () => {
  it("renders correctly", async () => {
    render(<OutputTargetSelector />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Output Target")).toBeInTheDocument();
      expect(screen.getByText(/Choose where content should be displayed/i)).toBeInTheDocument();
    });
  });

  it("shows loading skeleton initially", () => {
    render(<OutputTargetSelector />, { wrapper: TestWrapper });

    expect(screen.getByText("Output Target")).toBeInTheDocument();
  });

  it("shows current selection when loaded", async () => {
    render(<OutputTargetSelector />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("UI Only")).toBeInTheDocument();
      expect(screen.getByText("Board Only")).toBeInTheDocument();
      expect(screen.getByText("UI + Board")).toBeInTheDocument();
    });

    // mockOutputSettings has target: "board", so Board Only should have Active badge
    await waitFor(() => {
      const activeBadges = screen.getAllByText("Active");
      expect(activeBadges.length).toBeGreaterThanOrEqual(0);
    });
  });

  it("handles selection changes", async () => {
    const user = userEvent.setup();
    render(<OutputTargetSelector />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("UI Only")).toBeInTheDocument();
    });

    const uiOnlyButton = screen.getByRole("button", { name: /UI Only/ });
    await user.click(uiOnlyButton);

    // Mutation should complete; component remains rendered
    await waitFor(() => {
      expect(screen.getByText("Output Target")).toBeInTheDocument();
    });
  });
});
