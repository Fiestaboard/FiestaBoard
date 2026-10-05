/**
 * Change Page thumbnails for an LED board (a Pixoo): the batch preview is
 * asked for that board, so its colour spans and icons render, and the
 * thumbnail draws the answered `cells` rather than the message.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PageGridSelector } from "@/components/page-grid-selector";
import type { Page, PagePreviewBatchResponse } from "@/lib/api";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  api: {
    getPages: vi.fn(),
    getBoardSettings: vi.fn(),
    previewPagesBatch: vi.fn(),
    getCollections: vi.fn(),
  },
  isCollectionId: (id: string) => id?.startsWith("collection:"),
  COLLECTION_ID_PREFIX: "collection:",
}));

const PIXOO = {
  id: "px1",
  name: "Desk",
  device_type: "panel" as const,
  device_model: "divoom_pixoo64",
  grid_rows: 8,
  grid_cols: 10,
  enabled: true,
};

const board = vi.hoisted(() => ({ current: null as unknown }));
vi.mock("@/components/current-board-context", () => ({
  useCurrentBoard: () => ({ currentBoard: board.current, currentBoardId: null, setCurrentBoardId: () => {} }),
}));

const PAGE: Page = {
  id: "page-1",
  name: "Hot",
  type: "template",
  device_type: "panel",
  grid_rows: 8,
  grid_cols: 10,
  template: ["{{red:HOT}}"],
  duration_seconds: 300,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
};

const RESPONSE: PagePreviewBatchResponse = {
  previews: {
    "page-1": {
      page_id: "page-1",
      message: "{red:HOT}",
      lines: ["{red:HOT}"],
      display_type: "template",
      raw: {},
      available: true,
      cells: [[..."Hot"].map((value) => ({ type: "char", value, color: "red" }))],
    },
  },
  total: 1,
  successful: 1,
};

function Wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("Change Page thumbnails for an LED board", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    board.current = PIXOO;
    vi.mocked(api.getPages).mockResolvedValue({ pages: [PAGE], total: 1 });
    vi.mocked(api.getBoardSettings).mockResolvedValue({
      board_type: "black",
      boards: [PIXOO],
      devices: ["panel"],
    } as unknown as Awaited<ReturnType<typeof api.getBoardSettings>>);
    vi.mocked(api.getCollections).mockResolvedValue({ collections: [], total: 0 });
    vi.mocked(api.previewPagesBatch).mockResolvedValue(RESPONSE);
  });

  it("asks for the previews for the board and draws their cells", async () => {
    render(<PageGridSelector activePageId={null} onSelectPage={vi.fn()} />, { wrapper: Wrapper });
    await waitFor(() => expect(api.previewPagesBatch).toHaveBeenCalledWith(["page-1"], "px1"));
    // The cells' own case ("Hot"), which the message ("{red:HOT}") does not have.
    await waitFor(() =>
      expect(screen.getAllByRole("img").map((el) => el.getAttribute("aria-label"))).toContainEqual(
        expect.stringContaining("Hot"),
      ),
    );
  });

  it("previews an LED display's pages as LED while a split-flap board is selected", async () => {
    // The library shows every page; a page that fits only the Pixoo is still
    // drawn as the Pixoo, and asked for it, while the Flagship is selected.
    const flagship = { id: "vb1", name: "Hall", device_type: "flagship" as const, device_model: null, enabled: true };
    board.current = flagship;
    const flagPage: Page = {
      ...PAGE,
      id: "page-2",
      device_type: "flagship",
      grid_rows: undefined,
      grid_cols: undefined,
    };
    vi.mocked(api.getPages).mockResolvedValue({ pages: [PAGE, flagPage], total: 2 });
    vi.mocked(api.getBoardSettings).mockResolvedValue({
      board_type: "black",
      boards: [flagship, PIXOO],
      devices: ["flagship", "panel"],
    } as unknown as Awaited<ReturnType<typeof api.getBoardSettings>>);
    vi.mocked(api.previewPagesBatch).mockImplementation(async (ids: string[], boardId?: string) =>
      boardId ? RESPONSE : { previews: {}, total: ids.length, successful: 0 },
    );

    render(<PageGridSelector activePageId={null} onSelectPage={vi.fn()} />, { wrapper: Wrapper });

    await waitFor(() => expect(api.previewPagesBatch).toHaveBeenCalledWith(["page-1"], "px1"));
    expect(api.previewPagesBatch).toHaveBeenCalledWith(["page-2"]);
    await waitFor(() =>
      expect(screen.getAllByRole("img").map((el) => el.getAttribute("aria-label"))).toContainEqual(
        expect.stringContaining("Hot"),
      ),
    );
  });

  it("keeps a board's rich previews apart from the split-flap ones it caches", async () => {
    const { unmount } = render(<PageGridSelector activePageId={null} onSelectPage={vi.fn()} />, {
      wrapper: Wrapper,
    });
    await waitFor(() => expect(api.previewPagesBatch).toHaveBeenCalledTimes(1));
    unmount();
    // A split-flap board (no device model): the rich preview cached for the
    // Pixoo is not served; it asks again, without a board.
    board.current = { ...PIXOO, id: "vb1", device_model: null };
    render(<PageGridSelector activePageId={null} onSelectPage={vi.fn()} />, { wrapper: Wrapper });
    await waitFor(() => expect(api.previewPagesBatch).toHaveBeenLastCalledWith(["page-1"]));
  });
});
