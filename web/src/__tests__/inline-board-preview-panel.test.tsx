/**
 * An AI tool-call card previewing a panel page must render it at the panel's
 * grid: the render endpoint refuses a panel without grid_rows/grid_cols, and
 * the board has no implied size to fall back to.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { InlineBoardPreview } from "@/components/inline-board-preview";

import { server } from "./mocks/server";

function Wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

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
