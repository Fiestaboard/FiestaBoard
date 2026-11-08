import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { PageGridSelector } from "@/components/page-grid-selector";
import type { BoardInstance, Page, PagePreviewBatchResponse } from "@/lib/api";
import { api } from "@/lib/api";
import { resolveBoardModel } from "@/lib/device-preview";

vi.mock("@/lib/api", () => ({
  api: { getPages: vi.fn(), getBoardSettings: vi.fn(), previewPagesBatch: vi.fn(), getCollections: vi.fn() },
  isCollectionId: (id: string) => id?.startsWith("collection:"),
  COLLECTION_ID_PREFIX: "collection:",
}));
vi.mock("@/components/current-board-context", () => ({ useCurrentBoard: () => ({ currentBoard: undefined }) }));
vi.mock("@/components/device-preview", () => ({
  DevicePreview: ({ model, cells, layers }: { model: { id: string } | null; cells: unknown; layers: unknown }) => (
    <div
      data-testid="target-preview"
      data-model={model?.id}
      data-cells={JSON.stringify(cells)}
      data-layers={JSON.stringify(layers)}
    />
  ),
}));
const A = {
  id: "led-a",
  name: "A",
  device_type: "panel",
  device_model: "divoom_pixoo64",
  grid_rows: 8,
  grid_cols: 10,
  enabled: true,
} as BoardInstance;
const B = {
  ...A,
  id: "led-b",
  name: "B",
  device_model_spec: { ...resolveBoardModel(A)!, id: "second_led" },
} as BoardInstance;
const PAGE = {
  id: "shared",
  name: "Shared page",
  device_type: "panel",
  grid_rows: 8,
  grid_cols: 10,
  type: "template",
  template: ["Hi"],
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
} as Page;
function response(target: string): PagePreviewBatchResponse {
  return {
    previews: {
      shared: {
        page_id: "shared",
        available: true,
        message: target,
        lines: [target],
        display_type: "template",
        raw: {},
        cells: [[{ type: "char", value: target, color: "red" }]],
        layers: [{ x: 0, y: 0, width: 1, height: 1, rgba: target }],
      },
    },
    total: 1,
    successful: 1,
  };
}
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = (target: BoardInstance) => (
    <QueryClientProvider client={client}>
      <PageGridSelector compatibleBoard={target} onSelectPage={vi.fn()} showCollections={false} />
    </QueryClientProvider>
  );
  const rendered = render(view(A));
  return { ...rendered, select: (target: BoardInstance) => rendered.rerender(view(target)) };
}
async function expectTarget(target: BoardInstance) {
  await waitFor(() => {
    const preview = screen.getByTestId("target-preview");
    expect(preview).toHaveAttribute("data-model", resolveBoardModel(target)!.id);
    const expected = response(target.id).previews.shared;
    if (!expected.available) throw new Error("Expected successful preview fixture");
    expect(preview).toHaveAttribute("data-cells", JSON.stringify(expected.cells));
    expect(preview).toHaveAttribute("data-layers", JSON.stringify(expected.layers));
  });
}
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(api.getPages).mockResolvedValue({ pages: [PAGE], total: 1 });
  vi.mocked(api.getBoardSettings).mockResolvedValue({
    board_type: "black",
    boards: [A, B],
    devices: ["panel"],
  } as Awaited<ReturnType<typeof api.getBoardSettings>>);
  vi.mocked(api.getCollections).mockResolvedValue({ collections: [], total: 0 });
});
it("restores A's cells and layers with A's model after filtering A to B to A", async () => {
  vi.mocked(api.previewPagesBatch).mockImplementation(async (_ids, target) => response(target!));
  expect(resolveBoardModel(B)?.id).toBe("second_led");
  const { select } = setup();
  await expectTarget(A);
  select(B);
  await expectTarget(B);
  select(A);
  await expectTarget(A);
  expect(api.previewPagesBatch).toHaveBeenCalledTimes(2);
});
it("ignores a late response from a filter that is no longer selected", async () => {
  let resolveA!: (value: PagePreviewBatchResponse) => void;
  vi.mocked(api.previewPagesBatch).mockImplementation((_ids, target) =>
    target === A.id
      ? new Promise((resolve) => {
          resolveA = resolve;
        })
      : Promise.resolve(response(B.id)),
  );
  const { select } = setup();
  await waitFor(() => expect(api.previewPagesBatch).toHaveBeenCalledWith([PAGE.id], A.id));
  select(B);
  await expectTarget(B);
  await act(async () => {
    resolveA(response(A.id));
  });
  await expectTarget(B);
});
