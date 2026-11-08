import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { CurrentBoardProvider, useCurrentBoard } from "@/components/current-board-context";
import { PageBuilder } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import type { BoardInstance, BoardSettings, Page, TemplateRenderResponse } from "@/lib/api";
import { api } from "@/lib/api";

import { server } from "./mocks/server";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } }));
vi.mock("@/components/device-preview", () => ({
  DevicePreview: ({ layers }: { layers?: unknown }) => (
    <div data-testid="queue-preview" data-layers={JSON.stringify(layers)} />
  ),
}));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      renderTemplate: vi.fn(),
      getTemplateVariables: vi.fn(),
      getBoardSettings: vi.fn(),
      getPage: vi.fn(),
    },
  };
});
const A = {
  id: "pixel-a",
  name: "A",
  device_type: "panel",
  board_color: "black",
  enabled: true,
  api_mode: "virtual",
  output: "divoom_pixoo",
  device_model: "divoom_pixoo64",
  charset: "led_3x5",
  grid_rows: 10,
  grid_cols: 16,
} as BoardInstance;
const B = { ...A, id: "pixel-b", name: "B" };
const CANVAS = {
  id: "sky",
  area: { row: 1, col: 1, rows: 2, cols: 4 },
  bleed: [],
  scale: 1,
  text: "hide",
  content: { background: "#000000", palette: {}, shapes: [], pixels: [] },
};
const OLD_LAYER = { x: 0, y: 0, width: 1, height: 1, rgba: "AAAA" };
const NEW_LAYER = { ...OLD_LAYER, rgba: "BBBB" };
const blankResponse = (layers = [OLD_LAYER]): TemplateRenderResponse => ({
  rendered: "\n".repeat(9),
  lines: Array(10).fill(""),
  line_count: 10,
  layers,
  canvas_issues: [],
});
function SwitchBoard() {
  const { setCurrentBoardId } = useCurrentBoard();
  return <button onClick={() => setCurrentBoardId(B.id)}>Use board B</button>;
}
function Wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <CurrentBoardProvider>
        <ConfigOverridesProvider>
          <ThemeProvider attribute="class" defaultTheme="light">
            <SwitchBoard />
            {children}
          </ThemeProvider>
        </ConfigOverridesProvider>
      </CurrentBoardProvider>
    </QueryClientProvider>
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  localStorage.setItem("fiestaboard_current_board", A.id);
  vi.mocked(api.getBoardSettings).mockResolvedValue({
    board_type: "black",
    boards: [A, B],
    devices: ["panel"],
  } as BoardSettings);
  vi.mocked(api.getPage).mockResolvedValue({
    id: "canvas-only",
    name: "Canvas only",
    type: "template",
    device_type: "panel",
    grid_rows: 10,
    grid_cols: 16,
    template: Array(10).fill(""),
    line_metadata: Array.from({ length: 10 }, () => ({ alignment: "left", wrap: false })),
    duration_seconds: 30,
    created_at: "2026-01-01",
    canvases: [CANVAS],
  } as Page);
  vi.mocked(api.getTemplateVariables).mockResolvedValue({
    variables: {},
    max_lengths: {},
    colors: {},
    symbols: [],
    filters: [],
    formatting: {},
    syntax_examples: {},
  });
  server.use(http.get("/api/panels", () => HttpResponse.json({ panels: [], total: 0 })));
});
afterEach(() => vi.useRealTimers());
async function settleEditDebounce() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(320);
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(230);
  });
}
it.each(["blank response", "request error"])(
  "drains the latest canvas edit after an in-flight %s",
  async (completion) => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let resolveFirst!: (value: TemplateRenderResponse) => void;
    let rejectFirst!: (reason: Error) => void;
    vi.mocked(api.renderTemplate)
      .mockImplementationOnce(
        () =>
          new Promise((resolve, reject) => {
            resolveFirst = resolve;
            rejectFirst = reject;
          }),
      )
      .mockResolvedValue(blankResponse([NEW_LAYER]));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<PageBuilder pageId="canvas-only" onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: Wrapper });
    await waitFor(() => expect(api.renderTemplate).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole("button", { name: "Canvases" }));
    fireEvent.change(screen.getByLabelText("Canvas ID"), { target: { value: "intermediate-sky" } });
    fireEvent.change(screen.getByLabelText("Canvas ID"), { target: { value: "changed-sky" } });
    await settleEditDebounce();
    expect(api.renderTemplate).toHaveBeenCalledTimes(1);
    await act(async () => {
      if (completion === "blank response") resolveFirst(blankResponse());
      else rejectFirst(new Error("old render failed"));
    });
    await waitFor(() => expect(api.renderTemplate).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.renderTemplate).mock.calls[1][7]).toEqual([expect.objectContaining({ id: "changed-sky" })]);
    await waitFor(() =>
      expect(screen.getByTestId("queue-preview")).toHaveAttribute("data-layers", JSON.stringify([NEW_LAYER])),
    );
    expect(screen.queryByTestId("canvas-error")).not.toBeInTheDocument();
  },
);
it("drains a queued board change with the current target after a canvas-only response", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  let resolveFirst!: (value: TemplateRenderResponse) => void;
  vi.mocked(api.renderTemplate)
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveFirst = resolve;
        }),
    )
    .mockResolvedValue(blankResponse([NEW_LAYER]));
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  render(<PageBuilder pageId="canvas-only" onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: Wrapper });
  await waitFor(() => expect(api.renderTemplate).toHaveBeenCalledTimes(1));
  expect(vi.mocked(api.renderTemplate).mock.calls[0][6]).toBe(A.id);
  await user.click(screen.getByRole("button", { name: "Use board B" }));
  await settleEditDebounce();
  await act(async () => {
    resolveFirst(blankResponse());
  });
  await waitFor(() => expect(api.renderTemplate).toHaveBeenCalledTimes(2));
  expect(vi.mocked(api.renderTemplate).mock.calls[1][6]).toBe(B.id);
  await waitFor(() =>
    expect(screen.getByTestId("queue-preview")).toHaveAttribute("data-layers", JSON.stringify([NEW_LAYER])),
  );
});
