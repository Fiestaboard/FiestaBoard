/**
 * Any display with a custom grid is a page target — not only FiestaPanels.
 *
 * An output plugin's board (a Divoom Pixoo here) is stored as a custom grid,
 * a `panel` board of grid_rows × grid_cols. The editor's size picker lists it
 * by board name and model, picking it authors a `panel` page of its grid,
 * and while it is the target the editor is that board's: an LED preview, its
 * character set's extended markup offered (and only then), its case kept.
 *
 * A new page that asked for no device starts on the display selected in the
 * sidebar, whatever kind it is; an existing page keeps its own shape.
 */
import { tryResolveDeviceModel } from "@fiestaboard/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { PageBuilder } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import type { BoardInstance, BoardSettings, Page } from "@/lib/api";
import { api } from "@/lib/api";

import { server } from "./mocks/server";

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

const CURRENT_BOARD_KEY = "fiestaboard_current_board";

function TestWrapper({ children }: { children: ReactNode }) {
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

const FLAGSHIP: BoardInstance = {
  id: "flag-1",
  name: "Hall",
  device_type: "flagship",
  board_color: "black",
  enabled: true,
  api_mode: "local",
  host: "192.0.2.10",
  local_api_key: "***",
  cloud_key: "",
  output: "vestaboard",
  device_model: "vestaboard_flagship",
  charset: "vestaboard_v1",
} as BoardInstance;

const NOTE: BoardInstance = {
  ...FLAGSHIP,
  id: "note-1",
  name: "Desk note",
  device_type: "note",
  device_model: "vestaboard_note",
  charset: "vestaboard_v2",
} as BoardInstance;

const NOTE_ARRAY: BoardInstance = {
  ...FLAGSHIP,
  id: "arr-1",
  name: "Wall",
  device_type: "note_array",
  notes_wide: 2,
  notes_tall: 2,
  device_model: null,
  charset: null,
} as BoardInstance;

/** A Divoom Pixoo 64 as the output plugin stores it: a 10 × 16 custom grid. */
const PIXOO: BoardInstance = {
  ...FLAGSHIP,
  id: "pixoo-1",
  name: "Pixoo",
  device_type: "panel",
  grid_rows: 10,
  grid_cols: 16,
  api_mode: "virtual",
  output: "divoom_pixoo",
  device_model: "divoom_pixoo64",
  charset: "led_3x5",
} as BoardInstance;

const PIXOO_MODEL_LABEL = tryResolveDeviceModel("divoom_pixoo64").model!.label;
const PIXOO_OPTION = `Pixoo (${PIXOO_MODEL_LABEL} · 16×10 LED)`;

function settings(boards: BoardInstance[]): BoardSettings {
  return { board_type: "black", boards, devices: [...new Set(boards.map((b) => b.device_type))] };
}

function servePanels() {
  server.use(http.get("/api/panels", () => HttpResponse.json({ panels: [], total: 0 })));
}

function page(overrides: Partial<Page> = {}): Page {
  return {
    id: "page-1",
    name: "Hello",
    type: "template",
    device_type: "flagship",
    template: ["Hello there", "", "", "", "", ""],
    line_metadata: Array.from({ length: 6 }, () => ({ alignment: "left" as const, wrap: false })),
    duration_seconds: 30,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

const PIXOO_PAGE = page({
  device_type: "panel",
  grid_rows: 10,
  grid_cols: 16,
  template: ["Hello there", ...Array(9).fill("")],
  line_metadata: Array.from({ length: 10 }, () => ({ alignment: "left" as const, wrap: false })),
});

function renderNew() {
  return render(<PageBuilder onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });
}

function renderExisting() {
  return render(<PageBuilder pageId="page-1" onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });
}

async function openSizePicker(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByLabelText("Change board size"));
}

const lastRenderBoardId = () => vi.mocked(api.renderTemplate).mock.calls.at(-1)?.[6];

/** The size picker's trigger settles on `name` (the target is adopted once boards load). */
async function expectTarget(name: string) {
  const trigger = await screen.findByLabelText("Change board size");
  await waitFor(() => expect(trigger).toHaveTextContent(name));
}

describe("PageBuilder — any custom-grid display is a page target", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    servePanels();
    vi.mocked(api.getTemplateVariables).mockResolvedValue({
      variables: {},
      max_lengths: {},
      colors: { red: 63 },
      symbols: [],
      filters: [],
      formatting: {},
      syntax_examples: {},
    });
    vi.mocked(api.renderTemplate).mockResolvedValue({
      rendered: "Hello there",
      lines: ["Hello there"],
      line_count: 1,
    });
    vi.mocked(api.getBoardSettings).mockResolvedValue(settings([FLAGSHIP, PIXOO]));
    vi.mocked(api.getPage).mockResolvedValue(page());
  });

  describe("the size picker", () => {
    it("lists an output plugin's LED display by board name and model", async () => {
      const user = userEvent.setup();
      renderNew();
      await openSizePicker(user);

      expect(await screen.findByRole("option", { name: PIXOO_OPTION })).toBeInTheDocument();
      expect(screen.getByText("Your displays")).toBeInTheDocument();
    });

    it("lists no displays group when no board has a custom grid", async () => {
      vi.mocked(api.getBoardSettings).mockResolvedValue(settings([FLAGSHIP]));
      const user = userEvent.setup();
      renderNew();
      await openSizePicker(user);

      await screen.findByRole("option", { name: "Flagship" });
      expect(screen.queryByText("Your displays")).not.toBeInTheDocument();
    });

    it("sizes the page to the display's grid and previews it as that board", async () => {
      const user = userEvent.setup();
      const { container } = renderNew();
      await openSizePicker(user);
      await user.click(await screen.findByRole("option", { name: PIXOO_OPTION }));

      await waitFor(() => expect(screen.getByRole("img", { name: /10 rows by 16 columns/ })).toBeInTheDocument());
      await waitFor(() =>
        expect(container.querySelector('[data-slot="display-preview"]')).toHaveAttribute(
          "data-technology",
          "led_matrix",
        ),
      );
    });

    it("saves a page for the display as a panel page of its grid", async () => {
      vi.mocked(api.getPage).mockResolvedValue(PIXOO_PAGE);
      vi.mocked(api.updatePage).mockResolvedValue(PIXOO_PAGE);
      const user = userEvent.setup();
      renderExisting();

      // An existing page of the Pixoo's grid is named for the Pixoo.
      expect(await screen.findByLabelText("Change board size")).toHaveTextContent(PIXOO_OPTION);
      await user.click(await screen.findByRole("button", { name: /^Save/ }));
      await waitFor(() => expect(api.updatePage).toHaveBeenCalled());
      expect(vi.mocked(api.updatePage).mock.calls[0][1]).toMatchObject({
        device_type: "panel",
        grid_rows: 10,
        grid_cols: 16,
      });
    });
  });

  describe("with an LED display targeted", () => {
    beforeEach(() => {
      vi.mocked(api.getPage).mockResolvedValue(PIXOO_PAGE);
    });

    it("previews in the board's case, not uppercased", async () => {
      const { container } = renderExisting();
      await waitFor(() =>
        expect(container.querySelector('[data-slot="display-preview"]')).toHaveAttribute(
          "data-technology",
          "led_matrix",
        ),
      );
      await waitFor(() =>
        expect(screen.getAllByRole("img").map((el) => el.getAttribute("aria-label"))).toContainEqual(
          expect.stringContaining("Hello there"),
        ),
      );
    });

    it("keeps the editor's text in the case it was written", async () => {
      const { container } = renderExisting();
      const editor = await screen.findByRole("textbox", { name: "Template editor" }, { timeout: 5000 });
      await waitFor(() => expect(editor).toHaveTextContent("Hello there"));
      // The split-flap editor shows (and saves) everything uppercased; an LED
      // set that draws lowercase must not.
      expect(container.querySelector('[class*="ProseMirror]:uppercase"]')).toBeNull();
    });

    it("offers text colours, block colours and icons from the board's character set", async () => {
      const user = userEvent.setup();
      renderExisting();
      await screen.findByRole("textbox", { name: "Template editor" }, { timeout: 5000 });
      await user.click(screen.getByRole("button", { name: "Colors" }));

      expect(await screen.findByRole("group", { name: "Text colour" })).toBeInTheDocument();
      expect(screen.getByRole("group", { name: "Block colour" })).toBeInTheDocument();
      expect(screen.getByRole("group", { name: "Icons" })).toBeInTheDocument();
    });

    it("inserts an icon as {{icon:…}} markup into the page", async () => {
      const user = userEvent.setup();
      renderExisting();
      await screen.findByRole("textbox", { name: "Template editor" }, { timeout: 5000 });
      await user.click(screen.getByRole("button", { name: "Colors" }));
      const icons = await screen.findByRole("group", { name: "Icons" });
      await user.click(within(icons).getAllByRole("button")[0]);

      await waitFor(
        () => {
          const lines = vi.mocked(api.renderTemplate).mock.calls.at(-1)?.[0] as string[];
          expect(lines.join("\n")).toMatch(/\{\{icon:[a-z_]+\}\}/);
        },
        { timeout: 5000 },
      );
      expect(lastRenderBoardId()).toBe("pixoo-1");
    });
  });

  describe("with a split-flap board targeted", () => {
    it("offers no colour spans or icons, and keeps the flap editor", async () => {
      const user = userEvent.setup();
      const { container } = renderExisting();
      await waitFor(() => expect(api.renderTemplate).toHaveBeenCalled(), { timeout: 5000 });
      await user.click(await screen.findByRole("button", { name: "Colors" }, { timeout: 5000 }));

      await screen.findByLabelText("Color picker");
      expect(screen.queryByRole("group", { name: "Text colour" })).not.toBeInTheDocument();
      expect(screen.queryByRole("group", { name: "Icons" })).not.toBeInTheDocument();
      expect(container.querySelector('[class*="ProseMirror]:uppercase"]')).not.toBeNull();
    });
  });

  describe("a new page's default target", () => {
    it("is the selected LED display, at its exact grid, previewed as LED", async () => {
      localStorage.setItem(CURRENT_BOARD_KEY, "pixoo-1");
      const { container } = renderNew();

      await expectTarget(PIXOO_OPTION);
      await waitFor(() => expect(screen.getByRole("img", { name: /10 rows by 16 columns/ })).toBeInTheDocument());
      await waitFor(() =>
        expect(container.querySelector('[data-slot="display-preview"]')).toHaveAttribute(
          "data-technology",
          "led_matrix",
        ),
      );
    });

    it("is the selected split-flap board when that is the board in the sidebar", async () => {
      vi.mocked(api.getBoardSettings).mockResolvedValue(settings([PIXOO, NOTE]));
      localStorage.setItem(CURRENT_BOARD_KEY, "note-1");
      const { container } = renderNew();

      await expectTarget("Note");
      await waitFor(() => expect(screen.getByRole("img", { name: /3 rows by 15 columns/ })).toBeInTheDocument());
      expect(container.querySelector('[data-slot="display-preview"]')).not.toBeInTheDocument();
    });

    it("is the selected note array, at its notes wide × tall", async () => {
      vi.mocked(api.getBoardSettings).mockResolvedValue(settings([FLAGSHIP, NOTE_ARRAY, PIXOO]));
      localStorage.setItem(CURRENT_BOARD_KEY, "arr-1");
      renderNew();

      expect(await screen.findByLabelText("Notes wide")).toHaveTextContent("2 wide");
      expect(screen.getByLabelText("Notes tall")).toHaveTextContent("2 tall");
    });

    it("is the only display when there is just one", async () => {
      vi.mocked(api.getBoardSettings).mockResolvedValue(settings([PIXOO]));
      renderNew();

      await expectTarget(PIXOO_OPTION);
    });

    it("follows the sidebar: switching boards changes the next new page's target", async () => {
      vi.mocked(api.getBoardSettings).mockResolvedValue(settings([FLAGSHIP, NOTE, PIXOO]));
      localStorage.setItem(CURRENT_BOARD_KEY, "pixoo-1");
      const first = renderNew();
      await expectTarget(PIXOO_OPTION);
      first.unmount();

      localStorage.setItem(CURRENT_BOARD_KEY, "note-1");
      renderNew();
      await expectTarget("Note");
    });

    it("yields to a device the URL asked for", async () => {
      localStorage.setItem(CURRENT_BOARD_KEY, "pixoo-1");
      render(<PageBuilder deviceType="note" onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });

      expect(await screen.findByLabelText("Change board size")).toHaveTextContent("Note");
    });

    it("leaves an existing page on its own shape", async () => {
      localStorage.setItem(CURRENT_BOARD_KEY, "pixoo-1");
      renderExisting();

      await waitFor(() => expect(api.renderTemplate).toHaveBeenCalled(), { timeout: 5000 });
      expect(screen.getByLabelText("Change board size")).toHaveTextContent("Flagship");
      expect(lastRenderBoardId()).toBe("flag-1");
    });
  });
});
