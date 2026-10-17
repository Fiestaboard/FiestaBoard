/**
 * A display's own page (/displays/:boardId) shows the out-of-sync banner
 * under its "Now showing" preview (issue #1945), for that board: a secondary
 * board's banner saves in ITS geometry and says Restore resends every
 * display; the primary's has no such line; a FiestaPanel never shows it.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DisplayPage from "../../app/routes/displays.$boardId";
import { mockOutputs, mockStatus } from "./mocks/handlers";
import { server } from "./mocks/server";

const push = vi.fn();
const params: { boardId?: string } = {};

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn(), forward: vi.fn() }),
  useParams: () => params,
  usePathname: () => "/displays",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/smart-link", () => ({
  default: ({ children, href, ...rest }: { children: ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } }));

const API = "/api";

const LIVING = {
  id: "b1",
  name: "Living Room",
  device_type: "flagship",
  board_color: "black",
  output: "vestaboard",
  output_config: { api_mode: "local", host: "192.0.2.10", local_api_key: "***" },
};
const KITCHEN_WALL = {
  id: "b2",
  name: "Kitchen Wall",
  device_type: "note_array",
  notes_wide: 2,
  notes_tall: 1,
  board_color: "black",
  output: "vestaboard",
  output_config: { api_mode: "cloud" },
};
const TV = {
  id: "tv",
  name: "Hall TV",
  device_type: "panel",
  grid_rows: 12,
  grid_cols: 29,
  board_color: "black",
  output: "fiestapanel",
  output_config: {},
};

function grid(rows: number, cols: number, code: number) {
  return Array.from({ length: rows }, () => Array(cols).fill(code));
}

/** Board state per board id: `external` → what another app wrote. */
function serveBoards(
  boards: Record<string, unknown>[],
  states: Record<string, { rows: number; cols: number; external: boolean }>,
) {
  const created: Record<string, unknown>[] = [];
  server.use(
    http.get(`${API}/settings/board`, () => HttpResponse.json({ board_type: "black", boards, devices: [] })),
    http.get(`${API}/outputs`, () => HttpResponse.json(mockOutputs)),
    http.get(`${API}/v1/status`, () => HttpResponse.json({ ...mockStatus, boards: {} })),
    http.get(`${API}/panels`, () => HttpResponse.json({ panels: [], total: 0 })),
    http.get(`${API}/settings/hdmi-kiosk`, () =>
      HttpResponse.json({ supported: false, status: "unsupported", enabled: null }),
    ),
    http.get(`${API}/board/current-message`, ({ request }) => {
      const id = new URL(request.url).searchParams.get("board_id") ?? "b1";
      const s = states[id] ?? { rows: 6, cols: 22, external: false };
      const expected = grid(s.rows, s.cols, 2);
      const characters = s.external ? grid(s.rows, s.cols, 8) : expected;
      return HttpResponse.json({
        characters,
        message: "",
        rows: s.rows,
        cols: s.cols,
        expected_characters: expected,
        cached_at: null,
        api_mode: "local",
        board_id: id,
      });
    }),
    http.post(`${API}/v1/pages`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      created.push(body);
      return HttpResponse.json({ id: "new-page", ...body }, { status: 201 });
    }),
  );
  return created;
}

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DisplayPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  push.mockReset();
  delete params.boardId;
});

describe("/displays/:boardId out-of-sync banner", () => {
  it("shows the banner under a secondary board's preview and says Restore resends every display", async () => {
    serveBoards([LIVING, KITCHEN_WALL], { b2: { rows: 3, cols: 30, external: true } });
    params.boardId = "b2";
    renderPage();

    const banner = await screen.findByTestId("board-out-of-sync");
    expect(within(banner).getByText("Another app changed this board")).toBeInTheDocument();
    expect(within(banner).getByText("Restore resends pages to every display.")).toBeInTheDocument();
    // Under the "Now showing" preview, before the display's settings.
    const heading = screen.getByText("Now showing");
    const settings = await screen.findByTestId("board-card");
    expect(heading.compareDocumentPosition(banner) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(banner.compareDocumentPosition(settings) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("saves in the secondary board's own geometry", async () => {
    const created = serveBoards([LIVING, KITCHEN_WALL], { b2: { rows: 3, cols: 30, external: true } });
    params.boardId = "b2";
    const user = userEvent.setup();
    renderPage();

    const banner = await screen.findByTestId("board-out-of-sync");
    await user.click(within(banner).getByRole("button", { name: "Save as page" }));

    await waitFor(() => expect(created).toHaveLength(1));
    expect(created[0]).toMatchObject({ type: "template", device_type: "note_array", notes_wide: 2, notes_tall: 1 });
    expect(created[0].template).toEqual([
      "HHHHHHHHHHHHHHHHHHHHHHHHHHHHHH",
      "HHHHHHHHHHHHHHHHHHHHHHHHHHHHHH",
      "HHHHHHHHHHHHHHHHHHHHHHHHHHHHHH",
    ]);
  });

  it("shows the primary board's banner without the every-display line", async () => {
    serveBoards([LIVING, KITCHEN_WALL], { b1: { rows: 6, cols: 22, external: true } });
    params.boardId = "b1";
    renderPage();

    await screen.findByTestId("board-out-of-sync");
    expect(screen.queryByText("Restore resends pages to every display.")).toBeNull();
  });

  it("never shows the banner on a FiestaPanel, whose board always shows what was sent", async () => {
    serveBoards([LIVING, TV], {});
    params.boardId = "tv";
    renderPage();

    await screen.findByText("Now showing");
    await waitFor(() => expect(screen.getByTestId("display-panel-settings")).toBeInTheDocument());
    expect(screen.queryByTestId("board-out-of-sync")).toBeNull();
  });
});
