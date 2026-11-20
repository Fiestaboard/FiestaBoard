import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CollectionShowNow } from "@/components/collection-show-now";
import type { Collection } from "@/lib/api";

import { server } from "./mocks/server";

const state = vi.hoisted(() => ({ loading: false, empty: false }));
const board = { id: "secondary", name: "Lobby", device_type: "flagship", schedule_enabled: false };
vi.mock("@/components/current-board-context", () => ({
  useCurrentBoard: () => ({
    currentBoardId: "secondary",
    currentBoard: state.empty ? undefined : board,
    boards: state.empty ? [] : [{ id: "primary" }, board],
    isLoading: state.loading,
  }),
}));
const collection = { id: "collection:c1", name: "Rotation", page_ids: ["p1"] } as Collection;
const detail = {
  id: "secondary",
  active_page_id: "p1",
  schedule_enabled: false,
  override_started_at: "2026-01-01",
  override_expires_at: null,
};
function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CollectionShowNow collection={collection} onClose={vi.fn()} />
    </QueryClientProvider>,
  );
}
beforeEach(() => {
  state.loading = false;
  state.empty = false;
  server.use(
    http.get("/api/settings/board", () => HttpResponse.json({ boards: [{ id: "primary" }, board] })),
    http.get("/api/v1/boards/secondary", () => HttpResponse.json(detail)),
    http.get("/api/schedules/active/page", () =>
      HttpResponse.json({ schedule_enabled: false, temporary_override: { active: true, page_id: "p1" } }),
    ),
    http.get("/api/silence-status", () =>
      HttpResponse.json({ board_id: "secondary", active: true, ends_at_utc: "2026-12-01T08:00:00Z" }),
    ),
    http.get("/api/v1/pages", () =>
      HttpResponse.json({ pages: [{ id: "p1", name: "Morning", device_type: "flagship" }] }),
    ),
    http.get("/api/v1/collections", () => HttpResponse.json({ collections: [collection] })),
    http.get("/api/schedules", () => HttpResponse.json({ schedules: [] })),
  );
});
describe("Collection Show now safety", () => {
  it.each(["/api/settings/board", "/api/v1/boards/secondary", "/api/silence-status"])(
    "waits for %s before allowing Show now",
    async (path) => {
      let release!: () => void;
      let requested = false;
      const pending = new Promise<void>((resolve) => {
        release = resolve;
      });
      server.use(
        http.get(path, async () => {
          requested = true;
          await pending;
          return HttpResponse.json(
            path.includes("settings/board")
              ? { boards: [{ id: "primary" }, board] }
              : path.includes("v1/boards")
                ? detail
                : { active: false, board_id: "secondary" },
          );
        }),
      );
      if (path.includes("settings/board")) state.empty = true;
      mount();
      await waitFor(() => expect(requested).toBe(true));
      expect(screen.queryByRole("button", { name: "Show now" })).not.toBeInTheDocument();
      release();
      expect(await screen.findByRole("button", { name: "Show now" })).toBeInTheDocument();
      expect(screen.getByText(/Pick what Lobby shows/)).toBeInTheDocument();
    },
  );
  it.each(["/api/settings/board", "/api/v1/boards/secondary", "/api/silence-status"])(
    "blocks and permits retry after a rejected %s",
    async (path) => {
      server.use(http.get(path, () => HttpResponse.json({ detail: "Unavailable" }, { status: 500 })));
      mount();
      expect(await screen.findByRole("alert")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Show now" })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();
    },
  );
  it("warns about silence, clears the selected display override, then pins the saved Collection", async () => {
    const calls: string[] = [];
    server.use(
      http.delete("/api/settings/temporary-override", ({ request }) => {
        calls.push(`clear:${new URL(request.url).searchParams.get("board_id")}`);
        return HttpResponse.json({ active: false });
      }),
      http.put("/api/settings/active-page", async ({ request }) => {
        const body = (await request.json()) as { board_id: string; page_id: string };
        calls.push(`pin:${body.board_id}:${body.page_id}`);
        return HttpResponse.json({ status: "ok" });
      }),
    );
    mount();
    const button = await screen.findByRole("button", { name: "Show now" });
    expect(await screen.findByTestId("change-page-silence")).toBeInTheDocument();
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    await waitFor(() => expect(calls).toEqual(["clear:secondary", "pin:secondary:collection:c1"]));
  });
});

describe("Collection Show now during an Override (BB-A-7)", () => {
  it("still offers Until <next Schedule change>, which a new hold replaces the Override up to", async () => {
    const soon = new Date(Date.now() + 60 * 60_000).toISOString();
    server.use(
      http.get("/api/v1/boards/secondary", () =>
        HttpResponse.json({
          ...detail,
          schedule_enabled: true,
          schedule_next_change_at: soon,
          schedule_next_page_id: "p1",
        }),
      ),
      http.get("/api/schedules/active/page", () =>
        HttpResponse.json({ schedule_enabled: true, temporary_override: { active: true, page_id: "p1" } }),
      ),
    );
    mount();
    await waitFor(() =>
      expect(screen.getAllByRole("radio").some((r) => /^Until \d/.test(r.textContent?.trim() ?? ""))).toBe(true),
    );
  });
});
