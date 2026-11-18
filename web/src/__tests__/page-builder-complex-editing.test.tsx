/**
 * Web 2.9 (04b) wiring in the real page editor: a big board opens with the
 * zoom control, Go to and the truncation map; a note array gets Note focus;
 * and every board shows the hub's real-width overflow (H4) with a fix.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PageBuilder } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import type { BoardSettings, Page } from "@/lib/api";
import { api } from "@/lib/api";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } }));

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

const boardSettings: BoardSettings = {
  board_type: "black",
  boards: [
    {
      id: "board-1",
      name: "Kitchen board",
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

const basePage: Page = {
  id: "p1",
  revision: "r1",
  name: "Kitchen morning",
  type: "template",
  device_type: "flagship",
  template: ["GOOD MORNING", "N JUDAH {{muni.next}}", "", "", "", ""],
  duration_seconds: 300,
  created_at: new Date().toISOString(),
};

let validateBodies: Array<Record<string, unknown>> = [];

function stubValidate(errors: unknown[]) {
  validateBodies = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (String(url).includes("/templates/validate")) {
        validateBodies.push(JSON.parse(init!.body as string));
        return new Response(JSON.stringify({ valid: errors.length === 0, errors, rows: 6, cols: 22 }), {
          headers: { "content-type": "application/json" },
        });
      }
      return new Response(JSON.stringify({ detail: "not mocked" }), { status: 404 });
    }),
  );
}

function renderEditor(page: Page) {
  vi.mocked(api.getPage).mockResolvedValue(page);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          <PageBuilder pageId={page.id} onClose={vi.fn()} />
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>,
  );
}

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
  vi.mocked(api.renderTemplate).mockResolvedValue({ rendered: "GOOD MORNING", lines: ["GOOD MORNING"], line_count: 1 });
  vi.mocked(api.getBoardSettings).mockResolvedValue(boardSettings);
});

afterEach(() => vi.unstubAllGlobals());

describe("page editor complex editing (2.9)", () => {
  it("shows the hub's per-line overflow and wraps the line from the card", async () => {
    const user = userEvent.setup();
    stubValidate([{ line: 2, column: 22, message: "too long", code: "line_too_long", max_length: 24 }]);
    renderEditor(basePage);
    expect(await screen.findByText("Line 2")).toBeInTheDocument();
    expect(screen.getByText("24 of 22 columns · 2 cut off")).toBeInTheDocument();
    expect(validateBodies[0]).toMatchObject({ device_type: "flagship", board_id: "board-1" });
    await user.click(screen.getByRole("button", { name: "Wrap line 2" }));
    await waitFor(() =>
      expect(validateBodies.at(-1)).toMatchObject({
        line_metadata: expect.arrayContaining([expect.objectContaining({ wrap: true })]),
      }),
    );
    // A Flagship is not a big board: the plain Fit / Actual toggle stays.
    expect(screen.queryByRole("group", { name: "Preview zoom" })).toBeNull();
  });

  it("opens a 96 × 24 panel with zoom, Go to and the truncation map", async () => {
    stubValidate([]);
    renderEditor({
      ...basePage,
      id: "lobby",
      name: "Lobby this week",
      device_type: "panel",
      grid_rows: 24,
      grid_cols: 96,
      template: ["ROSA'S CAFE", ...Array.from({ length: 23 }, () => "")],
    });
    // The lenses are lazy chunks, and every role query walks the 2,304-tile
    // board, so under hosted coverage one poll can outlast findBy's 1 s
    // default. Wait for the first lens as long as the editor wait below; the
    // assertions themselves are unchanged.
    expect(await screen.findByRole("group", { name: "Preview zoom" }, { timeout: 10_000 })).toBeInTheDocument();
    expect(
      await screen.findByRole("textbox", { name: "Go to row and column" }, { timeout: 10_000 }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Where lines are cut")).toBeInTheDocument();
    // The template's line numbers keep AA contrast on a tall board (axe in the
    // 2.9 layout spec): muted colour, not muted colour at 40 % opacity.
    const editor = await screen.findByRole("textbox", { name: "Template editor" }, { timeout: 5000 });
    let node: Element | null = editor;
    while (node && node.previousElementSibling?.getAttribute("aria-hidden") !== "true") node = node.parentElement;
    const gutter = node!.previousElementSibling!;
    const numbers = Array.from(gutter.children) as HTMLElement[];
    expect(numbers.length).toBeGreaterThanOrEqual(24);
    for (const number of numbers) expect(number.style.opacity).toBe("");
  });

  it("gives a 2 × 2 note array Note focus and a seam check", async () => {
    stubValidate([]);
    renderEditor({
      ...basePage,
      id: "wall",
      name: "Lobby menu",
      device_type: "note_array",
      notes_wide: 2,
      notes_tall: 2,
      template: ["GOOD MORNING", "", "", "", "", ""],
    });
    expect(await screen.findByRole("radiogroup", { name: "Note focus" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "All notes" })).toBeChecked();
    expect(await screen.findByRole("status")).toHaveTextContent(/nothing straddles a seam/);
  });
});
