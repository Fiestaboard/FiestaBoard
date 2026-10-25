/**
 * The page editor previews and checks a page against the board it is for.
 *
 * A page belongs to a size; the board it is previewed as is the live-output
 * target or the board in context when the page fits it, else any board it
 * fits. That board's id goes on `POST /templates/render` (`board_id`), whose
 * `charset_issues` — cells the board's character set draws differently —
 * the editor shows beside its other warnings; and that board's model draws
 * the preview, so an LED board previews as an LED matrix.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PageBuilder } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import type { BoardInstance, BoardSettings, CharsetIssue, Page } from "@/lib/api";
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

const LED_SIGN: BoardInstance = {
  ...FLAGSHIP,
  id: "led-1",
  name: "Kitchen sign",
  device_type: "panel",
  grid_rows: 8,
  grid_cols: 10,
  device_model: "divoom_pixoo64",
  charset: "led_5x7",
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

const issue = (col: number, written: string, shown: string): CharsetIssue => ({
  row: 0,
  col,
  reason: "case",
  token: { type: "char", value: written },
  fallback: { type: "char", value: shown },
});

function renderEditor() {
  return render(<PageBuilder pageId="page-1" onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });
}

describe("PageBuilder board-aware preview", () => {
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
      rendered: "HI THERE",
      lines: ["HI THERE", "", "", "", "", ""],
      line_count: 6,
    });
    vi.mocked(api.getBoardSettings).mockResolvedValue(settings([FLAGSHIP]));
    vi.mocked(api.getPage).mockResolvedValue(page());
  });

  it("renders for the board the page fits, by id", async () => {
    renderEditor();
    await waitFor(() => expect(vi.mocked(api.renderTemplate).mock.calls.at(-1)?.[6]).toBe("board-1"), {
      timeout: 5000,
    });
  });

  it("names no board when the page fits none", async () => {
    vi.mocked(api.getPage).mockResolvedValue(page({ device_type: "note", template: ["Hi", "", ""] }));
    renderEditor();
    await waitFor(() => expect(api.renderTemplate).toHaveBeenCalled(), { timeout: 5000 });
    expect(vi.mocked(api.renderTemplate).mock.calls.at(-1)?.[6]).toBeNull();
  });

  it("shows the cells the board's character set draws differently", async () => {
    vi.mocked(api.renderTemplate).mockResolvedValue({
      rendered: "Hi there",
      lines: ["Hi there", "", "", "", "", ""],
      line_count: 6,
      charset: "vestaboard_v1",
      charset_issues: [issue(1, "i", "I")],
    });
    renderEditor();
    expect(
      await screen.findByText("Line 1, column 2: this board can't show “i” and draws “I” instead.", undefined, {
        timeout: 5000,
      }),
    ).toBeInTheDocument();
  });

  it("lists the first few issues and counts the rest", async () => {
    vi.mocked(api.renderTemplate).mockResolvedValue({
      rendered: "abcdefg",
      lines: ["abcdefg", "", "", "", "", ""],
      line_count: 6,
      charset: "vestaboard_v1",
      charset_issues: [..."abcdefg"].map((c, i) => issue(i, c, c.toUpperCase())),
    });
    renderEditor();
    expect(await screen.findByText("…and 2 more cells this board draws differently.", undefined, { timeout: 5000 }));
    expect(screen.getByTestId("charset-issues").querySelectorAll("span")).toHaveLength(1 + 5 + 1);
  });

  it("shows no charset warning when the board draws every cell", async () => {
    vi.mocked(api.renderTemplate).mockResolvedValue({
      rendered: "HI",
      lines: ["HI", "", "", "", "", ""],
      line_count: 6,
      charset: "vestaboard_v1",
      charset_issues: [],
    });
    renderEditor();
    await waitFor(() => expect(api.renderTemplate).toHaveBeenCalled(), { timeout: 5000 });
    expect(screen.queryByTestId("charset-issues")).not.toBeInTheDocument();
  });

  it("previews a page for an LED board as that board's LED matrix", async () => {
    vi.mocked(api.getBoardSettings).mockResolvedValue(settings([FLAGSHIP, LED_SIGN]));
    vi.mocked(api.getPage).mockResolvedValue(
      page({ device_type: "panel", grid_rows: 8, grid_cols: 10, template: Array.from({ length: 8 }, () => "") }),
    );
    const { container } = renderEditor();
    await waitFor(
      () =>
        expect(container.querySelector('[data-slot="display-preview"]')).toHaveAttribute(
          "data-technology",
          "led_matrix",
        ),
      { timeout: 5000 },
    );
  });

  it("checks a page for an LED board against that board", async () => {
    vi.mocked(api.getBoardSettings).mockResolvedValue(settings([FLAGSHIP, LED_SIGN]));
    vi.mocked(api.getPage).mockResolvedValue(
      page({ device_type: "panel", grid_rows: 8, grid_cols: 10, template: ["Hi", ...Array(7).fill("")] }),
    );
    renderEditor();
    await waitFor(() => expect(vi.mocked(api.renderTemplate).mock.calls.at(-1)?.[6]).toBe("led-1"), {
      timeout: 5000,
    });
  });

  it("previews a page for a split-flap board on the flaps, as before", async () => {
    const { container } = renderEditor();
    await waitFor(() => expect(api.renderTemplate).toHaveBeenCalled(), { timeout: 5000 });
    expect(container.querySelector('[data-slot="display-preview"]')).not.toBeInTheDocument();
    expect(container.querySelector("[data-board-preview]")).toBeInTheDocument();
  });
});
