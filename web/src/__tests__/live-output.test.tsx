import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

const defaultBoardSettings: BoardSettings = {
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

const multiBoardSettings: BoardSettings = {
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
    {
      id: "board-2",
      name: "Kitchen Note",
      device_type: "note",
      board_color: "white",
      enabled: true,
      api_mode: "cloud",
      host: "",
      local_api_key: "",
      cloud_key: "cloud-key-123",
    },
  ],
  devices: ["flagship", "note"],
};

describe("Live Output Mode", () => {
  const mockOnClose = vi.fn();
  const mockOnSave = vi.fn();

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
    vi.mocked(api.renderTemplateLive).mockResolvedValue({
      rendered: "test preview",
      lines: ["test preview"],
      line_count: 1,
      sent_to_board: true,
      board_id: "board-1",
    });
    vi.mocked(api.createPage).mockResolvedValue({
      status: "success",
      page: {
        id: "test-page-id",
        name: "Test Page",
        type: "template",
        device_type: "flagship",
        template: ["", "", "", "", "", ""],
        duration_seconds: 300,
        created_at: new Date().toISOString(),
      },
    });
    vi.mocked(api.getBoardSettings).mockResolvedValue(defaultBoardSettings);
    vi.mocked(api.forceRefresh).mockResolvedValue({
      status: "success",
      message: "Display force-refreshed successfully",
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders the live output toggle", async () => {
    render(<PageBuilder onClose={mockOnClose} onSave={mockOnSave} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Live Output")).toBeInTheDocument();
    });
  });

  it("renders the toggle switch with correct aria-label", async () => {
    render(<PageBuilder onClose={mockOnClose} onSave={mockOnSave} />, { wrapper: TestWrapper });

    await waitFor(() => {
      const toggle = screen.getByRole("switch", { name: /toggle live output to board/i });
      expect(toggle).toBeInTheDocument();
    });
  });

  it("toggle is off by default", async () => {
    render(<PageBuilder onClose={mockOnClose} onSave={mockOnSave} />, { wrapper: TestWrapper });

    await waitFor(() => {
      const toggle = screen.getByRole("switch", { name: /toggle live output to board/i });
      expect(toggle).toHaveAttribute("data-state", "unchecked");
    });
  });

  it("toggle can be turned on", async () => {
    const user = userEvent.setup();
    render(<PageBuilder onClose={mockOnClose} onSave={mockOnSave} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("switch", { name: /toggle live output to board/i })).toBeInTheDocument();
    });

    const toggle = screen.getByRole("switch", { name: /toggle live output to board/i });
    await user.click(toggle);

    await waitFor(() => {
      expect(toggle).toHaveAttribute("data-state", "checked");
    });
  });

  it("toggle can be turned off after being turned on", async () => {
    const user = userEvent.setup();
    render(<PageBuilder onClose={mockOnClose} onSave={mockOnSave} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("switch", { name: /toggle live output to board/i })).toBeInTheDocument();
    });

    const toggle = screen.getByRole("switch", { name: /toggle live output to board/i });

    await user.click(toggle);
    await waitFor(() => {
      expect(toggle).toHaveAttribute("data-state", "checked");
    });

    await user.click(toggle);
    await waitFor(() => {
      expect(toggle).toHaveAttribute("data-state", "unchecked");
    });
  });

  it("calls forceRefresh immediately when live output is toggled off", async () => {
    const user = userEvent.setup();
    render(<PageBuilder onClose={mockOnClose} onSave={mockOnSave} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("switch", { name: /toggle live output to board/i })).toBeInTheDocument();
    });

    const toggle = screen.getByRole("switch", { name: /toggle live output to board/i });

    // Turn on live output
    await user.click(toggle);
    await waitFor(() => {
      expect(toggle).toHaveAttribute("data-state", "checked");
    });

    vi.mocked(api.forceRefresh).mockClear();

    // Turn off live output
    await user.click(toggle);
    await waitFor(() => {
      expect(toggle).toHaveAttribute("data-state", "unchecked");
    });

    // forceRefresh should be called immediately to restore normal board state
    expect(vi.mocked(api.forceRefresh)).toHaveBeenCalled();
  });

  it("does not show board selector when only one board is configured", async () => {
    vi.mocked(api.getBoardSettings).mockResolvedValue(defaultBoardSettings);

    render(<PageBuilder onClose={mockOnClose} onSave={mockOnSave} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Live Output")).toBeInTheDocument();
    });

    expect(screen.queryByRole("combobox", { name: /select board/i })).not.toBeInTheDocument();
  });

  it("shows board selector when multiple boards are configured", async () => {
    vi.mocked(api.getBoardSettings).mockResolvedValue(multiBoardSettings);

    render(<PageBuilder onClose={mockOnClose} onSave={mockOnSave} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: /select board for live output/i })).toBeInTheDocument();
    });
  });

  it("does not call renderTemplateLive when toggle is off", async () => {
    render(<PageBuilder onClose={mockOnClose} onSave={mockOnSave} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Live Output")).toBeInTheDocument();
    });

    // Wait a bit for any debounced calls
    await new Promise((resolve) => setTimeout(resolve, 1500));

    expect(vi.mocked(api.renderTemplateLive)).not.toHaveBeenCalled();
  });

  it("shows preview label alongside live output controls", async () => {
    render(<PageBuilder onClose={mockOnClose} onSave={mockOnSave} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Preview")).toBeInTheDocument();
      expect(screen.getByText("Live Output")).toBeInTheDocument();
    });
  });

  it("shows board color toggle alongside live output", async () => {
    render(<PageBuilder onClose={mockOnClose} onSave={mockOnSave} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Board color")).toBeInTheDocument();
      expect(screen.getByLabelText("Preview as black board")).toBeInTheDocument();
      expect(screen.getByLabelText("Preview as white board")).toBeInTheDocument();
    });
  });
});

describe("Live Output API Client", () => {
  it("renderTemplateLive is a function on the api object", async () => {
    const { api: realApi } = (await vi.importActual("@/lib/api")) as { api: Record<string, unknown> };
    expect(typeof realApi.renderTemplateLive).toBe("function");
  });
});

describe("Live Output - Board Selector Interaction", () => {
  const mockOnClose = vi.fn();
  const mockOnSave = vi.fn();

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
      rendered: "test",
      lines: ["test"],
      line_count: 1,
    });
    vi.mocked(api.renderTemplateLive).mockResolvedValue({
      rendered: "test",
      lines: ["test"],
      line_count: 1,
      sent_to_board: true,
      board_id: "board-1",
    });
    vi.mocked(api.getBoardSettings).mockResolvedValue(multiBoardSettings);
    vi.mocked(api.forceRefresh).mockResolvedValue({
      status: "success",
      message: "Display force-refreshed successfully",
    });
    vi.mocked(api.createPage).mockResolvedValue({
      status: "success",
      page: {
        id: "test-page-id",
        name: "Test Page",
        type: "template",
        device_type: "flagship",
        template: ["", "", "", "", "", ""],
        duration_seconds: 300,
        created_at: new Date().toISOString(),
      },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("board selector is present with correct aria-label when multiple boards", async () => {
    render(<PageBuilder onClose={mockOnClose} onSave={mockOnSave} />, { wrapper: TestWrapper });

    await waitFor(() => {
      const selector = screen.getByRole("combobox", { name: /select board for live output/i });
      expect(selector).toBeInTheDocument();
    });
  });

  it("live output controls are within a bordered container", async () => {
    render(<PageBuilder onClose={mockOnClose} onSave={mockOnSave} />, { wrapper: TestWrapper });

    await waitFor(() => {
      const liveLabel = screen.getByText("Live Output");
      expect(liveLabel).toBeInTheDocument();
      const container = liveLabel.closest("div.rounded-lg");
      expect(container).toBeInTheDocument();
    });
  });
});

describe("Live Output - Auto-timeout", () => {
  const mockOnClose = vi.fn();
  const mockOnSave = vi.fn();

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
      rendered: "test",
      lines: ["test"],
      line_count: 1,
    });
    vi.mocked(api.renderTemplateLive).mockResolvedValue({
      rendered: "test",
      lines: ["test"],
      line_count: 1,
      sent_to_board: true,
      board_id: "board-1",
    });
    vi.mocked(api.getBoardSettings).mockResolvedValue(defaultBoardSettings);
    vi.mocked(api.forceRefresh).mockResolvedValue({
      status: "success",
      message: "Display force-refreshed successfully",
    });
    vi.mocked(api.createPage).mockResolvedValue({
      status: "success",
      page: {
        id: "test-page-id",
        name: "Test Page",
        type: "template",
        device_type: "flagship",
        template: ["", "", "", "", "", ""],
        duration_seconds: 300,
        created_at: new Date().toISOString(),
      },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("auto-disables live mode after 5 minutes of inactivity", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { act } = await import("@testing-library/react");

    render(<PageBuilder onClose={mockOnClose} onSave={mockOnSave} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("switch", { name: /toggle live output to board/i })).toBeInTheDocument();
    });

    const toggle = screen.getByRole("switch", { name: /toggle live output to board/i });
    await user.click(toggle);

    await waitFor(() => {
      expect(toggle).toHaveAttribute("data-state", "checked");
    });

    // Advance past the 5-minute timeout
    await act(async () => {
      vi.advanceTimersByTime(5 * 60 * 1000 + 100);
    });

    expect(toggle).toHaveAttribute("data-state", "unchecked");
  });

  it("does not auto-disable before the 5 minute timeout", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { act } = await import("@testing-library/react");

    render(<PageBuilder onClose={mockOnClose} onSave={mockOnSave} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("switch", { name: /toggle live output to board/i })).toBeInTheDocument();
    });

    const toggle = screen.getByRole("switch", { name: /toggle live output to board/i });
    await user.click(toggle);

    await waitFor(() => {
      expect(toggle).toHaveAttribute("data-state", "checked");
    });

    // Advance to just under 5 minutes
    await act(async () => {
      vi.advanceTimersByTime(4 * 60 * 1000);
    });

    // Should still be enabled
    expect(toggle).toHaveAttribute("data-state", "checked");
  });

  it("calls forceRefresh when auto-timeout disables live mode", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { act } = await import("@testing-library/react");

    render(<PageBuilder onClose={mockOnClose} onSave={mockOnSave} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("switch", { name: /toggle live output to board/i })).toBeInTheDocument();
    });

    const toggle = screen.getByRole("switch", { name: /toggle live output to board/i });
    await user.click(toggle);

    await waitFor(() => {
      expect(toggle).toHaveAttribute("data-state", "checked");
    });

    vi.mocked(api.forceRefresh).mockClear();

    // Advance past the 5-minute timeout
    await act(async () => {
      vi.advanceTimersByTime(5 * 60 * 1000 + 100);
    });

    expect(toggle).toHaveAttribute("data-state", "unchecked");
    // forceRefresh should be called to restore normal board state
    expect(vi.mocked(api.forceRefresh)).toHaveBeenCalled();
  });
});

describe("Live Output - Cleanup on unmount", () => {
  const mockOnClose = vi.fn();
  const mockOnSave = vi.fn();

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
      rendered: "test",
      lines: ["test"],
      line_count: 1,
    });
    vi.mocked(api.renderTemplateLive).mockResolvedValue({
      rendered: "test",
      lines: ["test"],
      line_count: 1,
      sent_to_board: true,
      board_id: "board-1",
    });
    vi.mocked(api.getBoardSettings).mockResolvedValue(defaultBoardSettings);
    vi.mocked(api.forceRefresh).mockResolvedValue({
      status: "success",
      message: "Display force-refreshed successfully",
    });
  });

  it("live mode state is destroyed when component unmounts (navigating away)", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<PageBuilder onClose={mockOnClose} onSave={mockOnSave} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("switch", { name: /toggle live output to board/i })).toBeInTheDocument();
    });

    const toggle = screen.getByRole("switch", { name: /toggle live output to board/i });
    await user.click(toggle);

    await waitFor(() => {
      expect(toggle).toHaveAttribute("data-state", "checked");
    });

    unmount();

    // Re-render - live mode should start as off (state was destroyed)
    render(<PageBuilder onClose={mockOnClose} onSave={mockOnSave} />, { wrapper: TestWrapper });

    await waitFor(
      () => {
        const newToggle = screen.getByRole("switch", { name: /toggle live output to board/i });
        expect(newToggle).toHaveAttribute("data-state", "unchecked");
      },
      { timeout: 10000 },
    );
  }, 15000);

  it("calls forceRefresh on unmount when live output was enabled", async () => {
    vi.mocked(api.forceRefresh).mockResolvedValue({
      status: "success",
      message: "Display force-refreshed successfully",
    });
    const user = userEvent.setup();
    const { unmount } = render(<PageBuilder onClose={mockOnClose} onSave={mockOnSave} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("switch", { name: /toggle live output to board/i })).toBeInTheDocument();
    });

    const toggle = screen.getByRole("switch", { name: /toggle live output to board/i });
    await user.click(toggle);

    await waitFor(() => {
      expect(toggle).toHaveAttribute("data-state", "checked");
    });

    unmount();

    expect(vi.mocked(api.forceRefresh)).toHaveBeenCalled();
  });

  it("does not call forceRefresh on unmount when live output was not enabled", async () => {
    vi.mocked(api.forceRefresh).mockResolvedValue({
      status: "success",
      message: "Display force-refreshed successfully",
    });
    const { unmount } = render(<PageBuilder onClose={mockOnClose} onSave={mockOnSave} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("switch", { name: /toggle live output to board/i })).toBeInTheDocument();
    });

    unmount();

    expect(vi.mocked(api.forceRefresh)).not.toHaveBeenCalled();
  });

  it("turns off live toggle when another tab clears the live-output channel", async () => {
    const user = userEvent.setup();
    render(<PageBuilder onClose={mockOnClose} onSave={mockOnSave} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("switch", { name: /toggle live output to board/i })).toBeInTheDocument();
    });

    const toggle = screen.getByRole("switch", { name: /toggle live output to board/i });
    await user.click(toggle);

    await waitFor(() => {
      expect(toggle).toHaveAttribute("data-state", "checked");
    });

    // Simulate another tab (e.g. the Home page kill switch) clearing the
    // shared live-output channel via localStorage. The page builder should
    // observe the storage event and turn off its own toggle so it stops
    // re-establishing live mode.
    // Use Event + defineProperty rather than `new StorageEvent("storage", { ... })`
    // — CodeQL flags the StorageEvent init-dict overload as superfluous
    // trailing arguments in the env, and jsdom's StorageEvent constructor
    // can be unreliable across versions.
    const storageEvent = new Event("storage");
    Object.defineProperty(storageEvent, "key", { value: "fiestaboard:liveOutputMessage" });
    Object.defineProperty(storageEvent, "newValue", { value: null });
    window.dispatchEvent(storageEvent);

    await waitFor(() => {
      expect(toggle).toHaveAttribute("data-state", "unchecked");
    });
  });
});
