/** Web 2.10 formula IDE seams in the page editor. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PageBuilder } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import type { BoardInstance, BoardSettings, Page } from "@/lib/api";
import { api } from "@/lib/api";
import { formulaDebugApi } from "@/lib/api/formula-debug";

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

const FLAGSHIP: BoardInstance = {
  id: "board-1",
  name: "Hall",
  device_type: "flagship",
  board_color: "black",
  enabled: true,
  api_mode: "local",
  host: "",
  local_api_key: "",
  cloud_key: "",
  note_array_token: "***",
  device_model: "vestaboard_flagship",
  charset: "vestaboard_v1",
} as BoardInstance;

function settings(boards: BoardInstance[]): BoardSettings {
  return { board_type: "black", boards, devices: [...new Set(boards.map((b) => b.device_type))] };
}

function page(overrides: Partial<Page> = {}): Page {
  return {
    id: "page-1",
    name: "Hot",
    type: "template",
    device_type: "flagship",
    template: ["Hi there", "", "", "", "", ""],
    line_metadata: Array.from({ length: 6 }, () => ({ alignment: "left" as const, wrap: false })),
    duration_seconds: 30,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

const FORMULA_PAGE = ["GOOD MORNING", '{{= IF(1 > 2, "HOT", "NICE") }} OUT', "", "", "", ""];

function renderEditor() {
  return render(<PageBuilder pageId="page-1" onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });
}

/**
 * Web 2.10: the formula values (H5) ride on the editor's own preview render.
 * In Live at the real time the formula IDE must not add a second
 * `/templates/render` per debounce: that duplicate render (and its re-render
 * of the page editor) is what slowed unrelated PageBuilder tests under load.
 */
describe("PageBuilder formula values on the preview render", () => {
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
      rendered: "GOOD MORNING\nNICE OUT",
      lines: ["GOOD MORNING", "NICE OUT", "", "", "", ""],
      line_count: 6,
    });
    vi.mocked(api.getBoardSettings).mockResolvedValue(settings([FLAGSHIP]));
  });

  it("asks the preview render for diagnostics when the page has a formula, and renders nothing else", async () => {
    const ideRender = vi.spyOn(formulaDebugApi, "render");
    vi.mocked(api.getPage).mockResolvedValue(page({ template: FORMULA_PAGE }));
    renderEditor();
    await waitFor(() => expect(api.renderTemplate).toHaveBeenCalled(), { timeout: 5000 });
    expect(vi.mocked(api.renderTemplate).mock.calls.at(-1)?.[8]).toEqual({ diagnostics: true });
    // Let any debounced follow-up settle before asserting nothing else rendered.
    await new Promise((resolve) => setTimeout(resolve, 600));
    expect(ideRender).not.toHaveBeenCalled();
  });

  it("leaves a page without formulas' preview request unchanged", async () => {
    vi.mocked(api.getPage).mockResolvedValue(page());
    renderEditor();
    await waitFor(() => expect(api.renderTemplate).toHaveBeenCalled(), { timeout: 5000 });
    expect(vi.mocked(api.renderTemplate).mock.calls.at(-1)?.[8]).toBeUndefined();
  });
});
