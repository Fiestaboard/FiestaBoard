/**
 * The page editor previews a grid page at its own text size.
 *
 * A Pixoo 64 set to the 8×10 Large face also draws 10×16 pages, in the 3×5
 * face. Editing such a page previews it as the board will draw it: the
 * preview model and LED layout are the 3×5 face's, and the canvases are
 * edited on that face's pixel grid. A page at the board's own grid previews
 * as the board is now.
 */
import { type DeviceModel, modelWithLedFont, tryResolveDeviceModel } from "@fiestaboard/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PageBuilder } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import type { BoardInstance, BoardSettings, Page } from "@/lib/api";
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
      getPage: vi.fn(),
      getBoardSettings: vi.fn(),
    },
  };
});

vi.mock("@/components/device-preview", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/components/device-preview")>()),
  DevicePreview: ({
    model,
    ledLayout,
    children,
  }: {
    model: { font?: string } | null;
    ledLayout?: { font?: string } | null;
    children: ReactNode;
  }) =>
    model ? (
      <div data-testid="device-preview" data-model-font={model.font} data-layout-font={ledLayout?.font} />
    ) : (
      <>{children}</>
    ),
}));

vi.mock("@/components/canvas-editor/canvases-panel", () => ({
  CanvasesPanel: ({ board }: { board: { font: string } }) => (
    <div data-testid="canvases-panel" data-board-font={board.font} />
  ),
}));

function TestWrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
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

// Core sends the model in the board's face (`device_model_spec`).
const PIXOO_IN_5x7 = modelWithLedFont(tryResolveDeviceModel("divoom_pixoo64").model as DeviceModel, "5x7");

const PIXOO_8x10: BoardInstance = {
  id: "led-1",
  name: "Kitchen sign",
  device_type: "panel",
  board_color: "black",
  enabled: true,
  api_mode: "local",
  host: "",
  local_api_key: "",
  cloud_key: "",
  note_array_token: "***",
  grid_rows: 8,
  grid_cols: 10,
  device_model: "divoom_pixoo64",
  device_model_spec: PIXOO_IN_5x7,
  charset: "led_5x7",
  producible_grids: { "5x7": [8, 10], "3x5": [10, 16] },
  led_layout: { tile_gap: "gap", block_padding: 0, font: "5x7" },
} as BoardInstance;

const settings = (boards: BoardInstance[]): BoardSettings => ({
  board_type: "black",
  boards,
  devices: [...new Set(boards.map((b) => b.device_type))],
});

function panelPage(rows: number, cols: number): Page {
  return {
    id: "page-1",
    name: "Weather",
    type: "template",
    device_type: "panel",
    grid_rows: rows,
    grid_cols: cols,
    template: Array.from({ length: rows }, () => ""),
    line_metadata: Array.from({ length: rows }, () => ({ alignment: "left" as const, wrap: false })),
    duration_seconds: 30,
    created_at: "2026-01-01T00:00:00Z",
  };
}

function renderEditor() {
  return render(<PageBuilder pageId="page-1" onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });
}

describe("PageBuilder previews a page at its own text size", () => {
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
    vi.mocked(api.renderTemplate).mockResolvedValue({ rendered: "", lines: [], line_count: 0 });
    vi.mocked(api.getBoardSettings).mockResolvedValue(settings([PIXOO_8x10]));
  });

  it("previews a 10x16 page on an 8x10 Pixoo in the 3x5 face", async () => {
    vi.mocked(api.getPage).mockResolvedValue(panelPage(10, 16));
    renderEditor();
    const preview = await screen.findByTestId("device-preview", undefined, { timeout: 5000 });
    expect([preview.dataset.modelFont, preview.dataset.layoutFont]).toEqual(["3x5", "3x5"]);
  });

  it("edits a 10x16 page's canvases on the 3x5 face's pixel grid", async () => {
    vi.mocked(api.getPage).mockResolvedValue(panelPage(10, 16));
    renderEditor();
    const panel = await screen.findByTestId("canvases-panel", undefined, { timeout: 5000 });
    expect(panel.dataset.boardFont).toBe("3x5");
  });

  it("previews a page at the board's own grid in the board's face", async () => {
    vi.mocked(api.getPage).mockResolvedValue(panelPage(8, 10));
    renderEditor();
    const preview = await screen.findByTestId("device-preview", undefined, { timeout: 5000 });
    expect([preview.dataset.modelFont, preview.dataset.layoutFont]).toEqual(["5x7", "5x7"]);
  });
});
