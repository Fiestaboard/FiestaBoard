/**
 * Pages a display can't produce are flagged, not hidden (flexible-pages spec
 * section 7): the picker and the Pages list show them greyed after the pages
 * that fit, with a plain reason, and a page that fits at another LED text
 * size previews in that size.
 */
import { modelWithLedFont, tryResolveDeviceModel } from "@fiestaboard/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PageGridSelector } from "@/components/page-grid-selector";
import type { BoardInstance, Page } from "@/lib/api";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  api: { getPages: vi.fn(), getBoardSettings: vi.fn(), previewPagesBatch: vi.fn(), getCollections: vi.fn() },
  isCollectionId: (id: string) => id?.startsWith("collection:"),
  COLLECTION_ID_PREFIX: "collection:",
}));

// A Pixoo 64 in the Large (5x7) face, as the API sends it: the model document
// in the board's face, so the 3x5 a 10x16 page needs can only come from the fit.
const PIXOO = {
  id: "px1",
  name: "Desk",
  device_type: "panel",
  device_model: "divoom_pixoo64",
  device_model_spec: modelWithLedFont(tryResolveDeviceModel("divoom_pixoo64").model!, "5x7"),
  grid_rows: 8,
  grid_cols: 10,
  enabled: true,
  producible_grids: { "5x7": [8, 10], "3x5": [10, 16] },
  led_layout: { tile_gap: "gap", block_padding: 0, font: "5x7" },
} as unknown as BoardInstance;

const board = vi.hoisted(() => ({ current: null as unknown }));
vi.mock("@/components/current-board-context", () => ({
  useCurrentBoard: () => ({ currentBoard: board.current, currentBoardId: null, setCurrentBoardId: () => {} }),
}));

vi.mock("@/components/device-preview", () => ({
  DevicePreview: ({
    model,
    ledLayout,
    children,
  }: {
    model: { font?: string } | null;
    ledLayout?: { font?: string } | null;
    children: React.ReactNode;
  }) =>
    model ? (
      <div data-testid="device-preview" data-model-font={model.font} data-layout-font={ledLayout?.font} />
    ) : (
      <>{children}</>
    ),
}));

function page(id: string, name: string, shape: Partial<Page>): Page {
  return {
    id,
    name,
    type: "template",
    template: [""],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...shape,
  } as Page;
}

const FLAG = page("flag", "Flagship page", { device_type: "flagship" });
const SMALL = page("small", "Small text page", { device_type: "panel", grid_rows: 10, grid_cols: 16 });
const LARGE = page("large", "Large text page", { device_type: "panel", grid_rows: 8, grid_cols: 10 });

function Wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("PageGridSelector flags pages a display can't show", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    board.current = PIXOO;
    vi.mocked(api.getPages).mockResolvedValue({ pages: [FLAG, SMALL, LARGE], total: 3 });
    vi.mocked(api.getBoardSettings).mockResolvedValue({
      board_type: "black",
      boards: [PIXOO],
      devices: ["panel"],
    } as unknown as Awaited<ReturnType<typeof api.getBoardSettings>>);
    vi.mocked(api.getCollections).mockResolvedValue({ collections: [], total: 0 });
    vi.mocked(api.previewPagesBatch).mockImplementation(async (ids: string[]) => ({
      previews: Object.fromEntries(
        ids.map((id) => [
          id,
          { page_id: id, message: "HI", lines: ["HI"], display_type: "template", raw: {}, available: true },
        ]),
      ),
      total: ids.length,
      successful: ids.length,
    }));
  });

  it("shows a page the board can't produce, greyed, with its reason", async () => {
    render(<PageGridSelector filterByCurrentBoardSize showCollections={false} onSelectPage={vi.fn()} />, {
      wrapper: Wrapper,
    });
    const card = await screen.findByRole("button", { name: /Flagship page/ });
    expect(card).toBeDisabled();
    expect(within(card).getByText("Made for a 6×22 board")).toBeInTheDocument();
  });

  it("lists misfits after the pages that fit", async () => {
    render(<PageGridSelector filterByCurrentBoardSize showCollections={false} onSelectPage={vi.fn()} />, {
      wrapper: Wrapper,
    });
    await screen.findByRole("button", { name: /Flagship page/ });
    const names = within(screen.getByRole("group", { name: "Pages" }))
      .getAllByRole("button")
      .map((button) => button.textContent ?? "")
      .map((text) => ["Flagship page", "Small text page", "Large text page"].find((name) => text.includes(name)));
    expect(names).toEqual(["Small text page", "Large text page", "Flagship page"]);
  });

  it("lets the Pages list open a misfit for editing", async () => {
    board.current = null;
    const onSelectPage = vi.fn();
    render(
      <PageGridSelector
        compatibleBoard={PIXOO}
        misfitsSelectable
        showCollections={false}
        onSelectPage={onSelectPage}
      />,
      { wrapper: Wrapper },
    );
    await userEvent.click(await screen.findByRole("button", { name: /Flagship page/ }));
    expect(onSelectPage).toHaveBeenCalledWith("flag");
  });

  it("says nothing fits and still lists the pages the board can't show", async () => {
    vi.mocked(api.getPages).mockResolvedValue({ pages: [FLAG], total: 1 });
    render(<PageGridSelector filterByCurrentBoardSize showCollections={false} onSelectPage={vi.fn()} />, {
      wrapper: Wrapper,
    });
    expect(await screen.findByText("No pages match this board's size.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Flagship page/ })).toHaveAccessibleDescription(/Made for a 6×22 board/);
  });

  it("flags a misfit in the list view too", async () => {
    render(
      <PageGridSelector filterByCurrentBoardSize viewMode="list" showCollections={false} onSelectPage={vi.fn()} />,
      { wrapper: Wrapper },
    );
    const item = await screen.findByRole("button", { name: /Flagship page/ });
    expect(item).toBeDisabled();
    expect(item).toHaveAccessibleDescription(/Made for a 6×22 board/);
  });

  it("previews a 10x16 page on an 8x10 Pixoo in the 3x5 face", async () => {
    render(<PageGridSelector filterByCurrentBoardSize showCollections={false} onSelectPage={vi.fn()} />, {
      wrapper: Wrapper,
    });
    const card = await screen.findByRole("button", { name: /Small text page/ });
    const preview = await within(card).findByTestId("device-preview");
    expect(preview).toHaveAttribute("data-model-font", "3x5");
    expect(preview).toHaveAttribute("data-layout-font", "3x5");
  });
});
