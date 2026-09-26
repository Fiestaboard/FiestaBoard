/**
 * The page-size picker offers FiestaPanels by name.
 *
 * A panel is the one board shape a user cannot reason about in Notes — it is
 * auto-fit from a TV's diagonal — so "Note Array, 2 wide, 4 tall" is not a
 * choice anyone can make correctly. Picking the panel by name sets the whole
 * geometry at once; the generic device choices stay for real hardware.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { PageBuilder } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import type { BoardSettings } from "@/lib/api";
import { api } from "@/lib/api";

import { server } from "./mocks/server";

const API_BASE = "/api";

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

// A flagship board only: the note-array seeding effect must not be what sets
// the grid in these tests — picking the panel must.
const boardSettings: BoardSettings = {
  board_type: "black",
  boards: [
    {
      id: "flag-1",
      name: "Flagship",
      device_type: "flagship",
      board_color: "black",
      enabled: true,
      api_mode: "local",
      host: "192.0.2.10",
      local_api_key: "***",
      cloud_key: "",
      notes_wide: 1,
      notes_tall: 1,
    },
  ],
  devices: ["flagship"],
};

function panel(id: string, name: string, notesWide: number, notesTall: number) {
  return {
    id,
    short_code: 1,
    name,
    board_id: `board-${id}`,
    screen_diagonal_inches: 55,
    calibration_scale: 1,
    animations_enabled: false,
    is_display: false,
    backdrop: "wall",
    auto_dim: { enabled: false, start: "22:00", end: "07:00" },
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    device_type: "note_array",
    board_missing: false,
    rows: notesTall * 3,
    cols: notesWide * 15,
    notes_wide: notesWide,
    notes_tall: notesTall,
  };
}

function servePanels(...panels: ReturnType<typeof panel>[]) {
  server.use(http.get(`${API_BASE}/panels`, () => HttpResponse.json({ panels, total: panels.length })));
}

async function openSizePicker(user: ReturnType<typeof userEvent.setup>) {
  const switcher = await screen.findByLabelText("Change board size");
  await user.click(switcher);
}

describe("PageBuilder size picker — FiestaPanels", () => {
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

  it("lists each panel by name and note grid", async () => {
    servePanels(panel("p1", "Kitchen TV", 2, 4), panel("p2", "Office TV", 3, 2));
    const user = userEvent.setup();
    render(<PageBuilder onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });

    await openSizePicker(user);

    expect(await screen.findByRole("option", { name: "Kitchen TV · 2×4 notes" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Office TV · 3×2 notes" })).toBeInTheDocument();
    expect(screen.getByText("Your panels")).toBeInTheDocument();
  });

  it("keeps the generic device choices below the panels", async () => {
    servePanels(panel("p1", "Kitchen TV", 2, 4));
    const user = userEvent.setup();
    render(<PageBuilder onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });

    await openSizePicker(user);

    await screen.findByRole("option", { name: "Kitchen TV · 2×4 notes" });
    for (const name of ["Flagship", "Note", "Note Array"]) {
      expect(screen.getByRole("option", { name })).toBeInTheDocument();
    }
  });

  it("sizes the page to the panel's grid when a panel is chosen", async () => {
    servePanels(panel("p1", "Kitchen TV", 2, 4));
    const user = userEvent.setup();
    render(<PageBuilder onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });

    await openSizePicker(user);
    await user.click(await screen.findByRole("option", { name: "Kitchen TV · 2×4 notes" }));

    // note_array + the panel's W×H, which is what the Notes selects report.
    await waitFor(() => expect(screen.getByLabelText("Notes wide")).toHaveTextContent("2 wide"));
    expect(screen.getByLabelText("Notes tall")).toHaveTextContent("4 tall");
    // The board is 4 Notes tall = 12 rows.
    expect(screen.getByRole("img", { name: /12 rows by 30 columns/ })).toBeInTheDocument();
  });

  it("keeps naming the chosen panel on the trigger, not the generic device type", async () => {
    // The Select is controlled, and a panel resolves to note_array + a grid.
    // If the value were the raw deviceType, the trigger would snap to
    // "Note Array" the instant the panel was chosen and reopening would
    // highlight the generic row — the picker would forget what was picked.
    servePanels(panel("p1", "Kitchen TV", 2, 4));
    const user = userEvent.setup();
    render(<PageBuilder onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });

    await openSizePicker(user);
    await user.click(await screen.findByRole("option", { name: "Kitchen TV · 2×4 notes" }));

    const switcher = await screen.findByLabelText("Change board size");
    await waitFor(() => expect(switcher).toHaveTextContent("Kitchen TV · 2×4 notes"));

    // Reopening shows the panel as the selected option, not "Note Array".
    await user.click(switcher);
    await waitFor(() =>
      expect(screen.getByRole("option", { name: "Kitchen TV · 2×4 notes" })).toHaveAttribute("aria-selected", "true"),
    );
    expect(screen.getByRole("option", { name: "Note Array" })).toHaveAttribute("aria-selected", "false");
  });

  it("shows no panels group at all on an install with no panels", async () => {
    servePanels();
    const user = userEvent.setup();
    render(<PageBuilder onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });

    await openSizePicker(user);

    // The picker is exactly the three generic sizes it has always been.
    await screen.findByRole("option", { name: "Flagship" });
    expect(screen.queryByText("Your panels")).not.toBeInTheDocument();
    expect(screen.getAllByRole("option")).toHaveLength(3);
  });
});
