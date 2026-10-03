/**
 * The page-size picker offers FiestaPanels by name.
 *
 * A panel is the one board shape a user cannot reason about by hand — it is
 * auto-fit per character from a TV's diagonal (a 55" TV is 12 × 29) — so it
 * is not a choice anyone can make correctly from the generic sizes. Picking
 * the panel by name sets the whole geometry at once: a "panel" page with the
 * panel's grid_rows × grid_cols. The generic device choices stay for real
 * hardware, and a legacy panel whose board is still a Note-block array keeps
 * resolving to a note_array page.
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
import type { BoardSettings, Page } from "@/lib/api";
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
      getPage: vi.fn(),
      updatePage: vi.fn(),
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

/** A per-character FiestaPanel board, as the API reports one. */
function panel(id: string, name: string, rows: number, cols: number) {
  return {
    ...legacyPanel(id, name, 1, 1),
    device_type: "panel",
    rows,
    cols,
    notes_wide: null,
    notes_tall: null,
  };
}

/** A panel created before per-character fitting: a Note-block array board. */
function legacyPanel(id: string, name: string, notesWide: number, notesTall: number) {
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

function servePanels(...panels: (ReturnType<typeof panel> | ReturnType<typeof legacyPanel>)[]) {
  server.use(http.get(`${API_BASE}/panels`, () => HttpResponse.json({ panels, total: panels.length })));
}

const existingFlagshipPage: Page = {
  id: "existing-1",
  name: "Existing Page",
  type: "template",
  device_type: "flagship",
  template: ["HELLO", "", "", "", "", ""],
  duration_seconds: 300,
  created_at: "2026-01-01T00:00:00Z",
};

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

  it("lists each panel by name and character grid", async () => {
    servePanels(panel("p1", "Kitchen TV", 12, 29), panel("p2", "Office TV", 14, 34));
    const user = userEvent.setup();
    render(<PageBuilder onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });

    await openSizePicker(user);

    expect(await screen.findByRole("option", { name: "Kitchen TV · 29×12" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Office TV · 34×14" })).toBeInTheDocument();
    expect(screen.getByText("Your panels")).toBeInTheDocument();
  });

  it("keeps the generic device choices below the panels", async () => {
    servePanels(panel("p1", "Kitchen TV", 12, 29));
    const user = userEvent.setup();
    render(<PageBuilder onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });

    await openSizePicker(user);

    await screen.findByRole("option", { name: "Kitchen TV · 29×12" });
    for (const name of ["Flagship", "Note", "Note Array"]) {
      expect(screen.getByRole("option", { name })).toBeInTheDocument();
    }
  });

  it("sizes the page to the panel's character grid when a panel is chosen", async () => {
    servePanels(panel("p1", "Kitchen TV", 12, 29));
    const user = userEvent.setup();
    render(<PageBuilder onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });

    await openSizePicker(user);
    await user.click(await screen.findByRole("option", { name: "Kitchen TV · 29×12" }));

    await waitFor(() => expect(screen.getByRole("img", { name: /12 rows by 29 columns, Panel/ })).toBeInTheDocument());
    // A panel is not a note array: the Notes selects do not apply to it.
    expect(screen.queryByLabelText("Notes wide")).not.toBeInTheDocument();
  });

  it("draws the preview at the panel's character grid", async () => {
    servePanels(panel("p1", "Kitchen TV", 12, 29));
    const user = userEvent.setup();
    render(<PageBuilder onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });

    await openSizePicker(user);
    await user.click(await screen.findByRole("option", { name: "Kitchen TV · 29×12" }));

    await waitFor(() => expect(document.querySelector('[data-testid="char-tile-11-28"]')).not.toBeNull());
    expect(document.querySelector('[data-testid="char-tile-0-29"]')).toBeNull();
  });

  it("previews a panel page with the panel's grid", async () => {
    servePanels(panel("p1", "Kitchen TV", 12, 29));
    vi.mocked(api.getPage).mockResolvedValue(existingFlagshipPage);
    const user = userEvent.setup();
    render(<PageBuilder pageId="existing-1" skipDraft onClose={vi.fn()} onSave={vi.fn()} />, {
      wrapper: TestWrapper,
    });
    await screen.findByText("6 × 22");

    await openSizePicker(user);
    await user.click(await screen.findByRole("option", { name: "Kitchen TV · 29×12" }));

    await waitFor(() =>
      expect(api.renderTemplate).toHaveBeenLastCalledWith(
        expect.anything(),
        expect.anything(),
        "panel",
        expect.anything(),
        expect.anything(),
        { rows: 12, cols: 29 },
      ),
    );
  });

  it("saves a panel page as device_type panel with the panel's grid_rows and grid_cols", async () => {
    servePanels(panel("p1", "Kitchen TV", 12, 29));
    vi.mocked(api.getPage).mockResolvedValue(existingFlagshipPage);
    vi.mocked(api.updatePage).mockResolvedValue({
      page: { ...existingFlagshipPage, device_type: "panel", grid_rows: 12, grid_cols: 29 },
      incompatible_references: [],
    });
    const user = userEvent.setup();
    render(<PageBuilder pageId="existing-1" skipDraft onClose={vi.fn()} onSave={vi.fn()} />, {
      wrapper: TestWrapper,
    });
    await screen.findByText("6 × 22");

    await openSizePicker(user);
    await user.click(await screen.findByRole("option", { name: "Kitchen TV · 29×12" }));
    await screen.findByText("12 × 29");

    // 6 × 22 → 12 × 29 grows on both axes, so no confirmation gate.
    await user.click(screen.getByRole("button", { name: "Save Page" }));
    await waitFor(() => expect(api.updatePage).toHaveBeenCalled());
    const [, payload] = vi.mocked(api.updatePage).mock.calls[0];
    expect(payload).toMatchObject({ device_type: "panel", grid_rows: 12, grid_cols: 29 });
    expect(payload).not.toHaveProperty("notes_wide");
    expect(payload).not.toHaveProperty("notes_tall");
  });

  it("keeps naming the chosen panel on the trigger, not the generic device type", async () => {
    // The Select is controlled, and a panel resolves to a device type + a
    // grid. If the value were the raw deviceType the trigger would forget
    // which panel was picked and reopening would highlight a generic row.
    servePanels(panel("p1", "Kitchen TV", 12, 29));
    const user = userEvent.setup();
    render(<PageBuilder onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });

    await openSizePicker(user);
    await user.click(await screen.findByRole("option", { name: "Kitchen TV · 29×12" }));

    const switcher = await screen.findByLabelText("Change board size");
    await waitFor(() => expect(switcher).toHaveTextContent("Kitchen TV · 29×12"));

    // Reopening shows the panel as the selected option.
    await user.click(switcher);
    await waitFor(() =>
      expect(screen.getByRole("option", { name: "Kitchen TV · 29×12" })).toHaveAttribute("aria-selected", "true"),
    );
    expect(screen.getByRole("option", { name: "Note Array" })).toHaveAttribute("aria-selected", "false");
  });

  it("names an unmatched panel page by its own grid when no panel fits it any more", async () => {
    // The page's panel was re-fit to another size (or deleted): the trigger
    // must still say what the page is rather than go blank.
    servePanels(panel("p1", "Kitchen TV", 14, 34));
    vi.mocked(api.getPage).mockResolvedValue({
      ...existingFlagshipPage,
      device_type: "panel",
      grid_rows: 12,
      grid_cols: 29,
      template: Array.from({ length: 12 }, () => ""),
    });
    render(<PageBuilder pageId="existing-1" skipDraft onClose={vi.fn()} onSave={vi.fn()} />, {
      wrapper: TestWrapper,
    });

    const switcher = await screen.findByLabelText("Change board size");
    await waitFor(() => expect(switcher).toHaveTextContent("Panel · 29×12"));
  });

  it("still sizes a legacy note-array panel's page as a note array", async () => {
    servePanels(legacyPanel("p1", "Kitchen TV", 2, 4));
    const user = userEvent.setup();
    render(<PageBuilder onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });

    await openSizePicker(user);
    await user.click(await screen.findByRole("option", { name: "Kitchen TV · 30×12" }));

    await waitFor(() => expect(screen.getByLabelText("Notes wide")).toHaveTextContent("2 wide"));
    expect(screen.getByLabelText("Notes tall")).toHaveTextContent("4 tall");
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
