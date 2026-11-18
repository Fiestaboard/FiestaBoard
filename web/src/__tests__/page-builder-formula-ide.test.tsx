/** Web 2.10 formula IDE seams in the page editor. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PageBuilder } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import type { BoardInstance, BoardSettings, Page } from "@/lib/api";
import { api } from "@/lib/api";
import { formulaDebugApi } from "@/lib/api/formula-debug";

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

  /**
   * FABLE-2541 M2: with "Mirror to board while editing" on, the live fast path
   * is the only render per edit, so the chip values must come from it. Before
   * the fix the IDE kept the last pre-mirroring diagnostics: an edited formula
   * lost its hint and unedited chips froze.
   */
  it("keeps chip values fresh from the live render while mirroring", async () => {
    const liveBodies: Array<Record<string, unknown>> = [];
    server.use(
      http.post("/api/templates/render/live", async ({ request }) => {
        const body = (await request.json()) as { template: string[]; diagnostics?: boolean };
        liveBodies.push(body);
        const source = /\{\{=\s*(.*?)\s*\}\}/.exec(body.template[1] ?? "")?.[1] ?? "";
        const value = source.includes("1 > 2") ? "NICE" : "HOT";
        return HttpResponse.json({
          rendered: `GOOD MORNING\n${value} OUT`,
          lines: ["GOOD MORNING", `${value} OUT`, "", "", "", ""],
          line_count: 6,
          sent_to_board: true,
          paused: false,
          silenced: false,
          board_id: "board-1",
          ...(body.diagnostics
            ? {
                diagnostics: {
                  formulas: [{ line: 2, start: 0, end: 30, source, value, error: null, error_at: null, message: null }],
                  lines: [],
                },
              }
            : {}),
        });
      }),
    );
    // The ordinary preview render (before mirroring) carries H5 values too.
    vi.mocked(api.renderTemplate).mockResolvedValue({
      rendered: "GOOD MORNING\nNICE OUT",
      lines: ["GOOD MORNING", "NICE OUT", "", "", "", ""],
      line_count: 6,
      diagnostics: {
        formulas: [
          {
            line: 2,
            start: 0,
            end: 30,
            source: 'IF(1 > 2, "HOT", "NICE")',
            value: "NICE",
            error: null,
            error_at: null,
            message: null,
          },
        ],
        lines: [],
      },
    });
    vi.mocked(api.getPage).mockResolvedValue(page({ template: FORMULA_PAGE }));
    renderEditor();
    expect(await screen.findByTestId("formula-atom-chip", undefined, { timeout: 5000 })).toHaveTextContent("= NICE");

    await userEvent.setup().click(screen.getByRole("switch", { name: /mirror to board while editing/i }));
    await waitFor(() => expect(liveBodies.length).toBeGreaterThan(0), { timeout: 5000 });
    expect(liveBodies.at(-1)).toMatchObject({ diagnostics: true });

    // Edit the formula's condition in the Plain editor (a real template change),
    // then return to Rich so the chip renders again.
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /plain text/i }));
    const plain = await screen.findByLabelText(/^template$/i, undefined, { timeout: 5000 });
    const before = liveBodies.length;
    fireEvent.change(plain, {
      target: { value: FORMULA_PAGE.join("\n").replace("1 > 2", "3 > 2") },
    });
    await waitFor(() => expect(liveBodies.length).toBeGreaterThan(before), { timeout: 5000 });
    expect((liveBodies.at(-1) as { template: string[] }).template[1]).toContain("3 > 2");
    await user.click(screen.getByRole("button", { name: /rich editor/i }));
    // The chip shows the value of the edited formula, from the live render.
    expect(await screen.findByTestId("formula-atom-chip", undefined, { timeout: 5000 })).toHaveTextContent("= HOT");
    expect(vi.mocked(api.renderTemplate).mock.calls.length).toBeLessThanOrEqual(1);
  });
});
