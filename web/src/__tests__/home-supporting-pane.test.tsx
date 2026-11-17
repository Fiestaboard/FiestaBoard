import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { toast } from "sonner";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { HomeSupportingPane } from "@/components/home/home-supporting-pane";
import type { BoardDetail, BoardInstance } from "@/lib/api";

import { server } from "./mocks/server";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock("@/components/smart-link", () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
const board = { id: "board-2", name: "Office", device_type: "flagship", enabled: true } as BoardInstance;
const detail = (extra = {}) =>
  ({
    next_change_at: new Date(Date.now() + 3600000).toISOString(),
    next_change_reason: "schedule",
    next_page_id: "page-2",
    ...extra,
  }) as BoardDetail;
const refresh = vi.fn();
function draw(extra: Record<string, unknown> = {}) {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}
    >
      <HomeSupportingPane
        board={board}
        scheduleEnabled={true}
        detail={detail()}
        pageName="Evening"
        nameOf={(id) => (id === "page-2" ? "Good night" : null)}
        refresh={refresh}
        {...extra}
      />
    </QueryClientProvider>,
  );
}
beforeEach(() => vi.clearAllMocks());
describe("Home supporting pane", () => {
  it("shows the one authoritative next event and display name", () => {
    draw();
    expect(screen.getByText("Good night")).toBeInTheDocument();
    expect(screen.getByText("Up next · Office")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View Schedule" })).toHaveAttribute("href", "/schedule");
  });
  it("names Schedule resuming when H2 says override_ends", () => {
    draw({ detail: detail({ next_change_reason: "override_ends" }) });
    expect(screen.getByText("Schedule resumes")).toBeInTheDocument();
    expect(screen.getByText("Good night")).toBeInTheDocument();
  });
  it.each([null, "bad-date", "2000-01-01T00:00:00Z"])("never invents an event for %s", (at) => {
    draw({ detail: detail({ next_change_at: at }) });
    expect(screen.queryByText("Good night")).not.toBeInTheDocument();
    expect(screen.getByText("No upcoming change reported by the hub.")).toBeInTheDocument();
  });
  it("does not invent a page name when H2 cannot name one", () => {
    draw({ detail: detail({ next_page_id: null }) });
    expect(screen.getByText("Schedule changes")).toBeInTheDocument();
  });
  it("does not offer an immediate switch before schedule state is known", () => {
    draw({ scheduleEnabled: undefined });
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
  });
  it("enables only this display, and Undo restores its Manual Mode", async () => {
    const writes: unknown[] = [];
    server.use(
      http.get("/api/v1/boards/board-2", () => HttpResponse.json({ schedule_enabled: true })),
      http.patch("/api/v1/boards/board-2", async ({ request }) => {
        writes.push(await request.json());
        return HttpResponse.json({ schedule_enabled: writes.length === 1 });
      }),
    );
    draw({ scheduleEnabled: false });
    fireEvent.click(screen.getByRole("switch", { name: "Schedule Mode" }));
    await waitFor(() => expect(writes).toEqual([{ schedule_enabled: true }]));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    const options = vi.mocked(toast.success).mock.calls[0][1];
    if (options?.action) await (options.action as unknown as { onClick: () => Promise<void> }).onClick();
    await waitFor(() => expect(writes).toEqual([{ schedule_enabled: true }, { schedule_enabled: false }]));
    expect(refresh).toHaveBeenCalled();
  });
  it("reports a failed switch without claiming Schedule Mode resumed", async () => {
    server.use(http.patch("/api/v1/boards/board-2", () => new HttpResponse(null, { status: 500 })));
    draw({ scheduleEnabled: false });
    fireEvent.click(screen.getByRole("switch", { name: "Schedule Mode" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(toast.success).not.toHaveBeenCalled();
  });
});

describe("Other displays", () => {
  it("selects another display using its own frame and mode without nested controls", async () => {
    server.use(
      http.get("/api/settings/board", () =>
        HttpResponse.json({ boards: [board, { ...board, id: "board-3", name: "Lobby" }] }),
      ),
      http.get("/api/schedules/active/page", ({ request }) =>
        HttpResponse.json({
          schedule_enabled: false,
          page_id: new URL(request.url).searchParams.get("board_id") === "board-3" ? "page-2" : null,
        }),
      ),
    );
    const { CurrentBoardProvider, useCurrentBoard } = await import("@/components/current-board-context");
    function Selection() {
      const { currentBoardId } = useCurrentBoard();
      return <output aria-label="Selected display">{currentBoardId}</output>;
    }
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <CurrentBoardProvider>
          <Selection />
          <HomeSupportingPane
            board={board}
            scheduleEnabled={true}
            detail={detail()}
            pageName="Evening"
            nameOf={(id) => (id === "page-2" ? "Good night" : null)}
            refresh={refresh}
          />
        </CurrentBoardProvider>
      </QueryClientProvider>,
    );
    const other = await screen.findByRole("button", { name: "Manage Lobby" });
    await waitFor(() => expect(other).toHaveTextContent("Manual Mode · Good night"));
    expect(other.querySelector("button, [tabindex='0']")).toBeNull();
    expect(screen.queryByRole("button", { name: "Manage Office" })).not.toBeInTheDocument();
    fireEvent.click(other);
    await waitFor(() => expect(screen.getByLabelText("Selected display")).toHaveTextContent("board-3"));
  });
});
