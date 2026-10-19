/**
 * An AI tool-call card previewing a panel page must render it at the panel's
 * grid: the render endpoint refuses a panel without grid_rows/grid_cols, and
 * the board has no implied size to fall back to.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { InlineBoardPreview } from "@/components/inline-board-preview";

import { server } from "./mocks/server";

function Wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const preview = vi.hoisted(() => ({ props: {} as Record<string, unknown> }));
vi.mock("@/components/device-preview", () => ({
  DevicePreview: (props: Record<string, unknown>) => {
    preview.props = props;
    return props.children;
  },
}));

const SNAPSHOT = { name: "Den", template: ["HELLO"], line_metadata: [] };

describe("InlineBoardPreview — panel", () => {
  it("renders a panel page with its grid_rows and grid_cols", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/templates/render", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ rendered: "HELLO", lines: ["HELLO"], line_count: 1 });
      }),
    );

    render(<InlineBoardPreview snapshot={SNAPSHOT} deviceType="panel" grid={{ rows: 12, cols: 29 }} />, {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ device_type: "panel", grid_rows: 12, grid_cols: 29 });
  });

  it("draws the board at the panel's row count", async () => {
    server.use(
      http.post("/api/templates/render", () =>
        HttpResponse.json({ rendered: "HELLO", lines: ["HELLO"], line_count: 1 }),
      ),
    );

    render(<InlineBoardPreview snapshot={SNAPSHOT} deviceType="panel" grid={{ rows: 12, cols: 29 }} />, {
      wrapper: Wrapper,
    });

    // The static (non-animating) board has no per-tile test ids: count the
    // rows of its tile grid instead.
    await waitFor(() => {
      const grid = document.querySelector('[aria-hidden="true"] > .flex.flex-col');
      expect(grid?.children).toHaveLength(12);
    });
  });
});

it("sends the draft board, note-array geometry and canvases to render", async () => {
  let body: Record<string, unknown> | null = null;
  server.use(
    http.post("/api/templates/render", async ({ request }) => {
      body = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ rendered: "", lines: [], line_count: 6, layers: [] });
    }),
  );
  const canvases = [{ id: "art", area: { row: 1, col: 1, rows: 1, cols: 2 }, content: { background: "#ff0000" } }];
  render(
    <InlineBoardPreview
      snapshot={{ ...SNAPSHOT, board_id: "pixels", device_type: "note_array", notes_wide: 2, notes_tall: 2, canvases }}
      deviceType="note_array"
    />,
    { wrapper: Wrapper },
  );
  await waitFor(() => expect(body).toMatchObject({ board_id: "pixels", notes_wide: 2, notes_tall: 2, canvases }));
});

it("draws returned canvas layers with the rendered markup", async () => {
  const rendered = "{red:a} {icon:sun}";
  const layers = [{ x: 0, y: 0, width: 1, height: 1, rgba: "/wAA/w==" }];
  server.use(
    http.post("/api/templates/render", () => HttpResponse.json({ rendered, lines: [rendered], line_count: 1, layers })),
  );
  render(<InlineBoardPreview snapshot={SNAPSHOT} deviceType="flagship" />, { wrapper: Wrapper });
  await waitFor(() => expect(preview.props).toMatchObject({ message: rendered, layers }));
});

it("renders again when only the draft artwork changes", async () => {
  const requests: Record<string, unknown>[] = [];
  server.use(
    http.post("/api/templates/render", async ({ request }) => {
      requests.push((await request.json()) as Record<string, unknown>);
      return HttpResponse.json({ rendered: "", lines: [], line_count: 1, layers: [] });
    }),
  );
  const canvas = (background: string) => [
    { id: "art", area: { row: 1, col: 1, rows: 1, cols: 2 }, content: { background } },
  ];
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = (background: string) => (
    <QueryClientProvider client={client}>
      <InlineBoardPreview snapshot={{ ...SNAPSHOT, canvases: canvas(background) }} deviceType="flagship" />
    </QueryClientProvider>
  );
  const { rerender } = render(view("#ff0000"));
  await waitFor(() => expect(requests).toHaveLength(1));
  rerender(view("#0000ff"));
  await waitFor(() => expect(requests).toHaveLength(2));
  expect(requests[1].canvases).toEqual(canvas("#0000ff"));
});
