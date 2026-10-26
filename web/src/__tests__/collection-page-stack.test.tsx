import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { CollectionPageStack } from "@/components/collection-page-stack";
import type { Collection, Page } from "@/lib/api";

import { server } from "./mocks/server";
vi.mock("@/components/device-preview", () => ({
  DevicePreview: ({
    model,
    cells,
    layers,
    children,
  }: {
    model: { id: string } | null;
    cells: unknown;
    layers: unknown;
    children: React.ReactNode;
  }) =>
    model ? (
      <div
        data-testid="led-preview"
        data-model={model.id}
        data-cells={JSON.stringify(cells)}
        data-layers={JSON.stringify(layers)}
      />
    ) : (
      children
    ),
}));
const cells = [[{ kind: "glyph", text: "A", color: "#00ff00", span: 2 }]];
const layers = [{ x: 0, y: 0, width: 1, height: 1, rgba: "AP8A/w==" }];
it("limits work to three actual LED members and preserves rich cells and bitmap layers", async () => {
  const requested: { page_ids: string[]; board_id?: string }[] = [];
  server.use(
    http.get("/api/settings/board", () =>
      HttpResponse.json({
        boards: [
          {
            id: "led",
            name: "Pixoo",
            device_type: "panel",
            grid_rows: 10,
            grid_cols: 16,
            device_model: "divoom_pixoo64",
            board_color: "black",
          },
        ],
      }),
    ),
    http.post("/api/pages/preview/batch", async ({ request }) => {
      const body = (await request.json()) as { page_ids: string[]; board_id?: string };
      requested.push(body);
      return HttpResponse.json({
        previews: Object.fromEntries(
          body.page_ids.map((id) => [id, { available: true, page_id: id, message: "A", cells, layers }]),
        ),
      });
    }),
  );
  const pages = Array.from({ length: 5 }, (_, index) => ({
    id: `p${index}`,
    name: `Page ${index}`,
    device_type: "panel",
    grid_rows: 10,
    grid_cols: 16,
  })) as Page[];
  const collection = { id: "collection:led", page_ids: pages.map((page) => page.id) } as Collection;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <CollectionPageStack collection={collection} pages={pages} />
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getAllByTestId("led-preview")).toHaveLength(3));
  expect(requested.at(-1)).toEqual({ page_ids: ["p0", "p1", "p2"], board_id: "led" });
  for (const preview of screen.getAllByTestId("led-preview")) {
    expect(preview).toHaveAttribute("data-model", "divoom_pixoo64");
    expect(preview).toHaveAttribute("data-cells", JSON.stringify(cells));
    expect(preview).toHaveAttribute("data-layers", JSON.stringify(layers));
  }
});
