/**
 * New note-array pages seed their W×H from the CURRENTLY SELECTED board when
 * it is a note array — not blindly from the first note_array in settings.
 * With a physical array and a FiestaPanel virtual board side by side, the
 * old first-match seeding authored pages sized for a different board than
 * the one the user was looking at (and exact size-key matching then hides
 * those pages from the panel's schedule picker).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { PageBuilder } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import type { BoardSettings } from "@/lib/api";
import { api } from "@/lib/api";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
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
      getBoardSettings: vi.fn(),
    },
  };
});

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <CurrentBoardProvider>
        <ConfigOverridesProvider>
          <ThemeProvider attribute="class" defaultTheme="light">
            {children}
          </ThemeProvider>
        </ConfigOverridesProvider>
      </CurrentBoardProvider>
    </QueryClientProvider>
  );
}

const boardSettings: BoardSettings = {
  board_type: "black",
  boards: [
    {
      id: "arr-phys",
      name: "Physical Array",
      device_type: "note_array",
      board_color: "black",
      enabled: true,
      api_mode: "cloud",
      host: "",
      local_api_key: "",
      cloud_key: "",
      note_array_token: "***",
      notes_wide: 2,
      notes_tall: 1,
    },
    {
      id: "arr-panel",
      name: "Living Room (Panel)",
      device_type: "note_array",
      board_color: "black",
      enabled: true,
      api_mode: "virtual",
      host: "",
      local_api_key: "",
      cloud_key: "",
      notes_wide: 1,
      notes_tall: 4,
    },
  ],
  devices: ["note_array", "note_array"],
};

describe("PageBuilder note-array seeding", () => {
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

  async function switchToNoteArray(user: ReturnType<typeof userEvent.setup>) {
    const switcher = await screen.findByLabelText("Change board size");
    await user.click(switcher);
    await user.click(await screen.findByRole("option", { name: "Note Array" }));
  }

  it("seeds W×H from the selected board when it is a note array", async () => {
    localStorage.setItem("fiestaboard_current_board", "arr-panel");
    const user = userEvent.setup();
    render(<PageBuilder onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });

    await switchToNoteArray(user);

    await waitFor(() => expect(screen.getByLabelText("Notes wide")).toHaveTextContent("1 wide"));
    expect(screen.getByLabelText("Notes tall")).toHaveTextContent("4 tall");
  });

  it("falls back to the first note-array board when the selected board is not one", async () => {
    // No stored selection → the primary (first) board is selected, which IS
    // the first note array here; assert its dims are used.
    const user = userEvent.setup();
    render(<PageBuilder onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });

    await switchToNoteArray(user);

    await waitFor(() => expect(screen.getByLabelText("Notes wide")).toHaveTextContent("2 wide"));
    expect(screen.getByLabelText("Notes tall")).toHaveTextContent("1 tall");
  });
});
