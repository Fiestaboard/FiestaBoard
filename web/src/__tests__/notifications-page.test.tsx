/**
 * Tests for notifications page.
 *
 * Covers: rendering, queue/history tabs, create, delete confirmation.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => "/notifications",
}));

import NotificationsPage from "@/app/notifications/page";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}

describe("NotificationsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders page header with title and description", async () => {
    render(<NotificationsPage />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Notifications")).toBeInTheDocument();
      expect(screen.getByText("Manage notification queue and history")).toBeInTheDocument();
    });
  });

  it("renders queue and history tabs", async () => {
    render(<NotificationsPage />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("tab", { name: /Queue/i })).toBeInTheDocument();
      expect(screen.getByRole("tab", { name: /History/i })).toBeInTheDocument();
    });
  });

  it("renders new notification button", async () => {
    render(<NotificationsPage />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("New Notification")).toBeInTheDocument();
    });
  });

  it("shows queued notification in queue tab", async () => {
    render(<NotificationsPage />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Test notification from HA")).toBeInTheDocument();
    });
  });

  it("shows expired notification in history tab", async () => {
    const user = userEvent.setup();
    render(<NotificationsPage />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("tab", { name: /History/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("tab", { name: /History/i }));

    await waitFor(() => {
      expect(screen.getByText("Old notification")).toBeInTheDocument();
    });
  });

  it("opens create notification sheet", async () => {
    const user = userEvent.setup();
    render(<NotificationsPage />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("New Notification")).toBeInTheDocument();
    });

    await user.click(screen.getByText("New Notification"));

    await waitFor(() => {
      expect(screen.getByLabelText("Message")).toBeInTheDocument();
      expect(screen.getByLabelText("Priority")).toBeInTheDocument();
      expect(screen.getByLabelText("Duration")).toBeInTheDocument();
    });
  });

  it("has delete buttons for notifications", async () => {
    render(<NotificationsPage />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Test notification from HA")).toBeInTheDocument();
    });

    // The notification card renders delete buttons with destructive styling
    const trashButtons = screen.getAllByRole("button").filter(
      (btn) => btn.className.includes("destructive")
    );
    expect(trashButtons.length).toBeGreaterThan(0);
  });
});
