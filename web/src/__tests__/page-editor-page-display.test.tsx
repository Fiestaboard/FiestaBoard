/**
 * UX-6-1 end to end (OPUS-2645 r2b M1): PageEditorShell carries the displays
 * the Creator IDE says show the page to the PageBuilder, so the preview and
 * the IDE both speak for the display the page is on. Real builder, real IDE:
 * three displays of the same grid, the page shown now on the second-listed
 * one, the sidebar on the third.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { PageEditorBridgeProvider } from "@/components/page-editor-bridge-context";
import { PageEditorShell } from "@/components/page-editor-shell";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import type { BoardInstance, Page } from "@/lib/api";
import { api } from "@/lib/api";

import { server } from "./mocks/server";

vi.unmock("react-router");
vi.mock("@/components/preview-target-popover", () => import("./mocks/preview-target-popover-inline"));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } }));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual("@/lib/api");
  return {
    ...actual,
    api: {
      ...(actual as { api: object }).api,
      renderTemplate: vi.fn(),
      getTemplateVariables: vi.fn(),
      getBoardSettings: vi.fn(),
      getPage: vi.fn(),
    },
  };
});

/** A 10 × 16 LED custom grid, as an output plugin stores it. */
const pixoo = (id: string, name: string) =>
  ({
    id,
    name,
    device_type: "panel",
    grid_rows: 10,
    grid_cols: 16,
    board_color: "black",
    enabled: true,
    api_mode: "virtual",
    host: "",
    local_api_key: "",
    cloud_key: "",
    output: "divoom_pixoo",
    device_model: "divoom_pixoo64",
    charset: "led_3x5",
  }) as BoardInstance;

// Same shape, all three fit the page. Attic is first in settings, Kitchen is
// the sidebar's board, Den (listed second) is the one the page shows on.
const BOARDS = [pixoo("attic", "Attic Pixoo"), pixoo("den", "Den Pixoo"), pixoo("kitchen", "Kitchen Pixoo")];

const PAGE: Page = {
  id: "page-1",
  name: "Commute",
  type: "template",
  device_type: "panel",
  grid_rows: 10,
  grid_cols: 16,
  template: ["NEXT TRAIN", ...Array(9).fill("")],
  line_metadata: Array.from({ length: 10 }, () => ({ alignment: "left" as const, wrap: false })),
  duration_seconds: 30,
  created_at: "2026-11-17T17:00:00Z",
};

/** The display each Problems-console check ran at. */
let validated: (string | undefined)[] = [];

beforeEach(() => {
  validated = [];
  vi.clearAllMocks();
  localStorage.clear();
  localStorage.setItem("fiestaboard_current_board", "kitchen");
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query.includes("min-width: 1024px"),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
  vi.mocked(api.getTemplateVariables).mockResolvedValue({
    variables: {},
    max_lengths: {},
    colors: {},
    symbols: [],
    filters: [],
    formatting: {},
    syntax_examples: {},
  });
  vi.mocked(api.renderTemplate).mockResolvedValue({ rendered: "NEXT TRAIN", lines: ["NEXT TRAIN"], line_count: 1 });
  vi.mocked(api.getBoardSettings).mockResolvedValue({ board_type: "black", boards: BOARDS, devices: ["panel"] });
  vi.mocked(api.getPage).mockResolvedValue(PAGE);
  server.use(
    http.get("/api/panels", () => HttpResponse.json({ panels: [], total: 0 })),
    http.get("/api/v1/collections", () => HttpResponse.json({ collections: [], total: 0 })),
    http.get("/api/v1/schedules", () =>
      HttpResponse.json({ schedules: [], total: 0, default_page_id: null, enabled: null }),
    ),
    http.get("/api/schedules/active/page", ({ request }) =>
      HttpResponse.json({
        page_id: new URL(request.url).searchParams.get("board_id") === "den" ? PAGE.id : "other",
        source: "manual",
        schedule_enabled: false,
        current_time: "07:41",
        current_day: "friday",
        default_page_id: null,
        temporary_override: { active: false },
      }),
    ),
    http.get("/api/pages/drafts", () => HttpResponse.json({ drafts: [] })),
    http.get(`/api/pages/${PAGE.id}/revisions`, () => HttpResponse.json({ page_id: PAGE.id, total: 0, revisions: [] })),
    http.get(`/api/pages/${PAGE.id}/sends`, () => HttpResponse.json({ page_id: PAGE.id, total: 0, sends: [] })),
    http.post("/api/templates/validate", async ({ request }) => {
      validated.push(((await request.json()) as { board_id?: string }).board_id);
      return HttpResponse.json({ valid: true, rows: 10, cols: 16, errors: [] });
    }),
  );
});

function renderShell() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const router = createMemoryRouter(
    [{ path: "*", element: <PageEditorShell pageId={PAGE.id} onClose={() => {}} onSave={() => {}} /> }],
    { initialEntries: [`/pages/edit/${PAGE.id}`] },
  );
  return render(
    <QueryClientProvider client={client}>
      <CurrentBoardProvider>
        <ConfigOverridesProvider>
          <ThemeProvider attribute="class" defaultTheme="light">
            <PageEditorBridgeProvider>
              <RouterProvider router={router} />
            </PageEditorBridgeProvider>
          </ThemeProvider>
        </ConfigOverridesProvider>
      </CurrentBoardProvider>
    </QueryClientProvider>,
  );
}

it("previews, names and checks the page as the display that shows it, not the sidebar's or the first", async () => {
  renderShell();
  // The editor's preview target (the size picker names the display).
  const picker = await screen.findByLabelText("Change board size");
  await waitFor(() => expect(picker).toHaveTextContent("Den Pixoo"), { timeout: 4000 });
  await waitFor(() => expect(vi.mocked(api.renderTemplate).mock.calls.at(-1)?.[6]).toBe("den"));
  // The Creator IDE speaks for the same display (it reads the editor's on its 1 s poll).
  const transition = await screen.findByRole("button", { name: /Transition/ });
  await waitFor(() => expect(transition).toHaveTextContent("Den Pixoo’s default"), { timeout: 3000 });
  expect(screen.getByText("Timeline · Commute this week · Den Pixoo")).toBeInTheDocument();
  expect(screen.queryByText(/Kitchen Pixoo’s default|Attic Pixoo’s default/)).not.toBeInTheDocument();
  await waitFor(() => expect(validated.at(-1)).toBe("den"), { timeout: 3000 });
});
