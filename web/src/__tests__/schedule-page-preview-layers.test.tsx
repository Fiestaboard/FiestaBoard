import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { SchedulePagePreview } from "@/components/schedule/schedule-page-preview";
import type { Page } from "@/lib/api";

import { server } from "./mocks/server";
const calls = vi.hoisted(() => [] as { layers?: unknown; model?: { id: string } }[]);
vi.mock("@/components/current-board-context", () => ({
  useCurrentBoard: () => ({
    boards: [{ id: "pixoo", device_type: "panel", device_model: "divoom_pixoo64", grid_rows: 8, grid_cols: 10 }],
    currentBoard: { id: "other", device_model: "vestaboard_flagship" },
  }),
}));
vi.mock("@/components/device-preview", () => ({
  DevicePreview: (props: { children: React.ReactNode; layers?: unknown; model?: { id: string } }) => {
    calls.push(props);
    return props.children;
  },
}));
vi.mock("@/components/board-viewport", () => ({
  BoardViewport: ({ message }: { message: string }) => <output>{message}</output>,
}));
describe("Schedule preview pixel evidence", () => {
  it("passes hub-rendered canvas layers and the explicit target model to the supported device renderer", async () => {
    const layers = [{ x: 0, y: 2, width: 1, height: 1, rgba: "/wAA/w==" }];
    server.use(
      http.post("/api/templates/render", () =>
        HttpResponse.json({ lines: ["PIXELS"], rendered: "PIXELS", line_count: 1, layers }),
      ),
    );
    const page = { id: "canvas-page", device_type: "panel", grid_rows: 8, grid_cols: 10, template: ["PIXELS"] } as Page;
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <SchedulePagePreview
          pageId={page.id}
          pages={[page]}
          boardId="pixoo"
          at="2026-11-17T02:18:00Z"
          label="Pixel preview"
        />
      </QueryClientProvider>,
    );
    await screen.findByText("PIXELS");
    expect(calls.at(-1)?.layers).toEqual(layers);
    expect(calls.at(-1)?.model?.id).toBe("divoom_pixoo64");
  });
});
