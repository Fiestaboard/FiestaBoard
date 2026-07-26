/**
 * Device/size switching in the page editor.
 *
 * New pages can pick their board size before saving. Since issue #1250,
 * EXISTING pages can be retargeted too: the switcher stays available, a
 * shrinking retarget asks for confirmation (conversion is lossy), and a
 * save whose response lists stale references (schedules / active pages on
 * boards the page no longer fits) surfaces a non-blocking warning.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PageBuilder } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import type { BoardSettings, Page } from "@/lib/api";
import { api } from "@/lib/api";

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

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

const existingFlagshipPage: Page = {
  id: "existing-1",
  name: "Existing Page",
  type: "template",
  device_type: "flagship",
  template: ["HELLO", "", "", "", "", ""],
  duration_seconds: 300,
  created_at: new Date().toISOString(),
};

const existingNotePage: Page = {
  ...existingFlagshipPage,
  id: "existing-2",
  device_type: "note",
  template: ["HI", "", ""],
};

async function switchDeviceTo(user: ReturnType<typeof userEvent.setup>, optionName: string) {
  const switcher = screen.getByLabelText("Change board size");
  await user.click(switcher);
  const option = await screen.findByRole("option", { name: optionName });
  await user.click(option);
}

describe("Page editor board-size switching", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
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

    await switchDeviceTo(user, "Note");

    // The editor now previews at note dimensions.
    await waitFor(() => {
      expect(screen.getByText("3 × 15")).toBeInTheDocument();
    });
    expect(screen.queryByText("6 × 22")).not.toBeInTheDocument();
  });

  it("offers the switcher on an existing page and confirms a shrinking retarget before saving", async () => {
    const user = userEvent.setup();
    vi.mocked(api.getPage).mockResolvedValue(existingFlagshipPage);
    vi.mocked(api.updatePage).mockResolvedValue({
      status: "success",
      page: { ...existingFlagshipPage, device_type: "note" },
      incompatible_references: [],
    });

    render(<PageBuilder pageId="existing-1" skipDraft onClose={vi.fn()} onSave={vi.fn()} />, {
      wrapper: TestWrapper,
    });

    await waitFor(() => {
      expect(screen.getByText("6 × 22")).toBeInTheDocument();
    });

    // The switcher is no longer hidden for saved pages.
    await switchDeviceTo(user, "Note");
    await waitFor(() => {
      expect(screen.getByText("3 × 15")).toBeInTheDocument();
    });

    // Saving a 6×22 -> 3×15 retarget is lossy: a confirmation gate appears
    // and nothing is saved until it is accepted.
    await user.click(screen.getByRole("button", { name: "Save Page" }));
    expect(api.updatePage).not.toHaveBeenCalled();
    expect(await screen.findByText("Change board size?")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Resize and save" }));
    await waitFor(() => {
      expect(api.updatePage).toHaveBeenCalledWith("existing-1", expect.objectContaining({ device_type: "note" }));
    });
  });

  it("saves a growing retarget without a confirmation gate", async () => {
    const user = userEvent.setup();
    vi.mocked(api.getPage).mockResolvedValue(existingNotePage);
    vi.mocked(api.updatePage).mockResolvedValue({
      status: "success",
      page: { ...existingNotePage, device_type: "flagship" },
      incompatible_references: [],
    });

    render(<PageBuilder pageId="existing-2" skipDraft onClose={vi.fn()} onSave={vi.fn()} />, {
      wrapper: TestWrapper,
    });

    await waitFor(() => {
      expect(screen.getByText("3 × 15")).toBeInTheDocument();
    });

    await switchDeviceTo(user, "Flagship");
    await waitFor(() => {
      expect(screen.getByText("6 × 22")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Save Page" }));
    await waitFor(() => {
      expect(api.updatePage).toHaveBeenCalledWith("existing-2", expect.objectContaining({ device_type: "flagship" }));
    });
    expect(screen.queryByText("Change board size?")).not.toBeInTheDocument();
  });

  it("warns (non-blocking) when the save response lists now-incompatible references", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    vi.mocked(api.getPage).mockResolvedValue(existingFlagshipPage);
    vi.mocked(api.updatePage).mockResolvedValue({
      status: "success",
      page: { ...existingFlagshipPage, device_type: "note" },
      incompatible_references: [
        { board_id: "board-1", board_name: "Kitchen", surface: "schedule", schedule_id: "sched-1" },
        { board_id: "board-2", board_name: "Office", surface: "active_page", schedule_id: null },
      ],
    });

    render(<PageBuilder pageId="existing-1" skipDraft onClose={onClose} onSave={vi.fn()} />, {
      wrapper: TestWrapper,
    });

    await waitFor(() => {
      expect(screen.getByText("6 × 22")).toBeInTheDocument();
    });

    await switchDeviceTo(user, "Note");
    await user.click(screen.getByRole("button", { name: "Save Page" }));
    await user.click(await screen.findByRole("button", { name: "Resize and save" }));

    // The save still succeeds (editor closes) and the stale refs surface as
    // a warning listing each board and where the page is referenced.
    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
    expect(toast.warning).toHaveBeenCalledTimes(1);
    const warned = vi.mocked(toast.warning).mock.calls[0][0] as string;
    expect(warned).toContain("Kitchen");
    expect(warned).toContain("schedule entry");
    expect(warned).toContain("Office");
    expect(warned).toContain("active page");
  });
});
