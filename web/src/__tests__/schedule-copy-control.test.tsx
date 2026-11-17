import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { ScheduleCopy } from "@/components/schedule/schedule-copy";
import type { Page } from "@/lib/api";

import { server } from "./mocks/server";
vi.mock("@/components/current-board-context", () => ({
  useCurrentBoard: () => ({
    boards: [
      { id: "source", name: "Source display", device_type: "flagship" },
      { id: "target", name: "Target display", device_type: "note" },
    ],
    currentBoard: { id: "source", name: "Source display", device_type: "flagship" },
  }),
}));
describe("Empty Schedule copy control", () => {
  it("copies compatible entries to the explicitly displayed board and prevents a duplicate submission", async () => {
    let write: Record<string, unknown> = {};
    server.use(
      http.get("/api/v1/schedules", ({ request }) => {
        expect(new URL(request.url).searchParams.get("board_id")).toBe("source");
        return HttpResponse.json({
          schedules: [
            {
              id: "old",
              page_id: "note-page",
              start_time: "09:00",
              end_time: "13:00",
              day_pattern: "all",
              enabled: true,
            },
          ],
        });
      }),
      http.post("/api/v1/schedules", async ({ request }) => {
        write = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...write, id: "new" });
      }),
    );
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ScheduleCopy
          boardId="target"
          pages={[{ id: "note-page", name: "Note page", device_type: "note" }] as Page[]}
          collections={[]}
        />
      </QueryClientProvider>,
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Copy from another display…" }));
    await user.click(screen.getByRole("combobox", { name: "Source display" }));
    await user.click(await screen.findByRole("option", { name: "Source display" }));
    const copy = screen.getByRole("button", { name: "Copy entries" });
    await waitFor(() => expect(copy).toBeEnabled());
    await user.click(copy);
    await waitFor(() => expect(write.board_id).toBe("target"));
    await waitFor(() => expect(copy).toBeDisabled());
  });
});
