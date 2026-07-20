/**
 * Device/size switching in the page creator (TDD for the "page creator can't
 * change board size" gap).
 *
 * A NEW page's device type is currently locked to the Pages tab the user
 * came from. These tests specify the desired behavior: the editor offers a
 * board-size switcher for new pages (so starting on the wrong tab is
 * recoverable), and keeps the size locked for existing pages (conversion of
 * saved content is lossy and stays out of scope).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PageBuilder } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import type { BoardSettings } from "@/lib/api";
import { api } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual("@/lib/api");
  return {
    ...actual,
    api: {
      ...(actual as { api: object }).api,
      renderTemplate: vi.fn(),
      renderTemplateLive: vi.fn(),
      getTemplateVariables: vi.fn(),
      createPage: vi.fn(),
      updatePage: vi.fn(),
      getPage: vi.fn(),
      getBoardSettings: vi.fn(),
      forceRefresh: vi.fn(),
    },
  };
});

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

const boardSettings: BoardSettings = {
  board_type: "black",
  boards: [
    {
      id: "board-1",
      name: "Living Room",
      device_type: "flagship",
      board_color: "black",
      enabled: true,
      api_mode: "local",
      host: "192.168.1.100",
      local_api_key: "test-key",
      cloud_key: "",
    },
  ],
  devices: ["flagship"],
};

describe("Page creator board-size switching", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getTemplateVariables).mockResolvedValue({
      variables: {},
      max_lengths: {},
      colors: {},
      symbols: [],
      filters: [],
      formatting: {},
      syntax_examples: {},
    });
    vi.mocked(api.renderTemplate).mockResolvedValue({
      rendered: "test preview",
      lines: ["test preview"],
      line_count: 1,
    });
    vi.mocked(api.getBoardSettings).mockResolvedValue(boardSettings);
  });

  it("lets a new page switch from Flagship to Note and resizes the grid to 3 × 15", async () => {
    const user = userEvent.setup();
    render(<PageBuilder onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });

    // Starts at flagship dimensions.
    await waitFor(() => {
      expect(screen.getByText("6 × 22")).toBeInTheDocument();
    });

    const switcher = screen.getByLabelText("Change board size");
    await user.click(switcher);
    const noteOption = await screen.findByRole("option", { name: "Note" });
    await user.click(noteOption);

    // The editor now previews at note dimensions.
    await waitFor(() => {
      expect(screen.getByText("3 × 15")).toBeInTheDocument();
    });
    expect(screen.queryByText("6 × 22")).not.toBeInTheDocument();
  });

  it("keeps the size locked for existing pages (no switcher)", async () => {
    vi.mocked(api.getPage).mockResolvedValue({
      id: "existing-1",
      name: "Existing Page",
      type: "template",
      device_type: "flagship",
      template: ["HELLO", "", "", "", "", ""],
      duration_seconds: 300,
      created_at: new Date().toISOString(),
    });

    render(<PageBuilder pageId="existing-1" onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("6 × 22")).toBeInTheDocument();
    });
    expect(screen.queryByLabelText("Change board size")).not.toBeInTheDocument();
  });
});
