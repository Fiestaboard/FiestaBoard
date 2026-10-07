/**
 * The page editor's pixel canvases (design PIXEL_CANVAS.md §5): edited and
 * previewed (server render with the board's layers) on an LED pixel board,
 * saved with the page; hidden on any other board, where a page that has
 * them says why their areas are blank.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
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
      createPage: vi.fn(),
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

const lastRenderBoardId = () => vi.mocked(api.renderTemplate).mock.calls.at(-1)?.[6];

// The page editor draws its preview through DevicePreview, which hands an LED
// board to FiestaUI's DisplayPreview; record the layers each is handed.
const devicePreviewProps: Array<{ layers?: unknown }> = [];
vi.mock("@/components/device-preview", async () => {
  const actual = await vi.importActual<typeof import("@/components/device-preview")>("@/components/device-preview");
  return {
    DevicePreview: (props: Parameters<typeof actual.DevicePreview>[0]) => {
      devicePreviewProps.push({ layers: props.layers });
      return <actual.DevicePreview {...props} />;
    },
  };
});
const displayPreviewLayers: unknown[] = [];
vi.mock("@fiestaboard/ui", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@fiestaboard/ui")>();
  return {
    ...actual,
    DisplayPreview: (props: Parameters<typeof actual.DisplayPreview>[0]) => {
      displayPreviewLayers.push(props.layers);
      return <actual.DisplayPreview {...props} />;
    },
  };
});

const SKY = {
  id: "sky",
  area: { row: 1, col: 1, rows: 2, cols: 4 },
  bleed: [],
  scale: 1,
  text: "hide" as const,
  content: { background: "#000000", palette: {}, shapes: [], pixels: [] },
};
const LAYER = { x: 0, y: 2, width: 15, height: 11, rgba: "AAAA" };

function renderExisting() {
  return render(<PageBuilder pageId="page-1" onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });
}

const lastRenderCanvases = () => vi.mocked(api.renderTemplate).mock.calls.at(-1)?.[7];

describe("PageBuilder — pixel canvases", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    devicePreviewProps.length = 0;
    displayPreviewLayers.length = 0;
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
      layers: [LAYER],
      canvas_issues: [],
    });
    vi.mocked(api.getBoardSettings).mockResolvedValue(settings([FLAGSHIP, PIXOO]));
  });

  describe("on an LED pixel board", () => {
    beforeEach(() => {
      vi.mocked(api.getPage).mockResolvedValue({ ...PIXOO_PAGE, canvases: [SKY] });
    });

    it("shows the canvas panel with the page's canvases", async () => {
      renderExisting();
      expect(await screen.findByTestId("canvases-panel", {}, { timeout: 5000 })).toBeInTheDocument();
      expect(screen.getByTestId("canvas-editor-sky")).toBeInTheDocument();
    });

    it("previews the canvases on the server for the board and hands the layers to the preview", async () => {
      renderExisting();
      await waitFor(() => expect(lastRenderCanvases()).toEqual([SKY]), { timeout: 5000 });
      expect(lastRenderBoardId()).toBe("pixoo-1");
      await waitFor(() => expect(devicePreviewProps.at(-1)?.layers).toEqual([LAYER]));
    });

    it("draws the layers in FiestaUI's preview, with no text-only notice", async () => {
      renderExisting();
      await waitFor(() => expect(displayPreviewLayers.at(-1)).toEqual([LAYER]), { timeout: 5000 });
      expect(screen.queryByText(/shows the text only/i)).not.toBeInTheDocument();
    });

    it("shows the canvas issues the preview reports", async () => {
      vi.mocked(api.renderTemplate).mockResolvedValue({
        rendered: "Hello there",
        lines: ["Hello there"],
        line_count: 1,
        layers: [],
        canvas_issues: [{ canvas_id: "sky", path: "source", message: "no such variable" }],
      });
      renderExisting();
      expect(await screen.findByTestId("canvas-issues", {}, { timeout: 5000 })).toHaveTextContent(
        "sky · source: no such variable",
      );
    });

    it("shows the server's refusal of the canvases", async () => {
      vi.mocked(api.renderTemplate).mockRejectedValue(new Error("shapes[0].x must be a number"));
      renderExisting();
      expect(await screen.findByTestId("canvas-error", {}, { timeout: 5000 })).toHaveTextContent(
        "shapes[0].x must be a number",
      );
    });

    it("adds a canvas and saves it with the page", async () => {
      vi.mocked(api.getPage).mockResolvedValue(PIXOO_PAGE);
      vi.mocked(api.updatePage).mockResolvedValue({ page: PIXOO_PAGE, incompatible_references: [] });
      const user = userEvent.setup();
      renderExisting();
      await user.click(await screen.findByRole("button", { name: "Add canvas" }, { timeout: 5000 }));
      await waitFor(() => expect(lastRenderCanvases()).toEqual([expect.objectContaining({ id: "canvas1" })]), {
        timeout: 5000,
      });
      await user.click(screen.getByRole("button", { name: /^Save/ }));
      await waitFor(() => expect(api.updatePage).toHaveBeenCalled());
      expect(vi.mocked(api.updatePage).mock.calls[0][1].canvases).toEqual([
        expect.objectContaining({ id: "canvas1", area: { row: 1, col: 1, rows: 5, cols: 8 } }),
      ]);
    });

    it("saves null once every canvas is deleted", async () => {
      vi.mocked(api.updatePage).mockResolvedValue({ page: PIXOO_PAGE, incompatible_references: [] });
      const user = userEvent.setup();
      renderExisting();
      await user.click(await screen.findByRole("button", { name: "Delete canvas sky" }, { timeout: 5000 }));
      await user.click(screen.getByRole("button", { name: /^Save/ }));
      await waitFor(() => expect(api.updatePage).toHaveBeenCalled());
      expect(vi.mocked(api.updatePage).mock.calls[0][1].canvases).toBeNull();
    });

    it("marks the canvas's first row in the plain template view, outside the text", async () => {
      const user = userEvent.setup();
      renderExisting();
      await screen.findByTestId("canvases-panel", {}, { timeout: 5000 });
      await user.click(screen.getByRole("button", { name: "Plain Text" }));
      const markers = await screen.findByTestId("line-markers");
      expect(markers).toHaveTextContent("{canvas:sky}");
      expect(screen.getByRole("textbox", { name: "" })).not.toHaveValue(expect.stringContaining("{canvas:"));
    });
  });

  describe("on a split-flap board", () => {
    it("hides the canvas editor and says why a page's canvases are blank", async () => {
      vi.mocked(api.getPage).mockResolvedValue(page({ canvases: [SKY] }));
      vi.mocked(api.getBoardSettings).mockResolvedValue(settings([FLAGSHIP]));
      renderExisting();
      expect(await screen.findByTestId("canvas-not-pixel-notice", {}, { timeout: 5000 })).toHaveTextContent(
        "can't draw them",
      );
      expect(screen.queryByTestId("canvases-panel")).not.toBeInTheDocument();
    });

    it("shows no notice for a page without canvases", async () => {
      vi.mocked(api.getPage).mockResolvedValue(page());
      vi.mocked(api.getBoardSettings).mockResolvedValue(settings([FLAGSHIP]));
      renderExisting();
      await waitFor(() => expect(api.renderTemplate).toHaveBeenCalled(), { timeout: 5000 });
      expect(screen.queryByTestId("canvas-not-pixel-notice")).not.toBeInTheDocument();
      expect(lastRenderCanvases()).toBeUndefined();
    });
  });
});
