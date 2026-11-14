// Review fixes for slice 2.2 (pr-2481-review): per-display Cancel and Undo
// (m08, m09, m11, S2), the next-change chip while an Override runs (m23, m24),
// the key guards (m21, m22) and the alert's plugin name (S4).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { toast } from "sonner";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ActivePageDisplay } from "@/components/active-page-display";
import { CurrentBoardProvider } from "@/components/current-board-context";
import { HomeCompose } from "@/components/home/home-compose";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const API = "/api";

vi.mock("@/components/smart-link", () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock("sonner", async () => {
  const actual = await vi.importActual<typeof import("sonner")>("sonner");
  return {
    ...actual,
    toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }),
  };
});

function Wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          <CurrentBoardProvider>{children}</CurrentBoardProvider>
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}

const TWO_BOARDS = {
  board_type: "black",
  boards: [
    { id: "board-1", name: "Kitchen board", device_type: "flagship", board_color: "black", enabled: true },
    { id: "board-2", name: "Office board", device_type: "flagship", board_color: "black", enabled: true },
  ],
  devices: ["flagship"],
};

const override = (extra: Record<string, unknown> = {}) => ({
  active: true,
  page_id: "page-2",
  expires_at: new Date(Date.now() + 30 * 60_000).toISOString(),
  started_at: new Date(Date.now() - 60_000).toISOString(),
  remaining_seconds: 1800,
  revert_mode: "page",
  revert_page_id: "page-1",
  ...extra,
});

/** The Office display has an Override; H2 also predicts a Schedule change. */
function serveOfficeOverride() {
  const nineLater = new Date(Date.now() + 2 * 60 * 60_000).toISOString();
  server.use(
    http.get(`${API}/settings/board`, () => HttpResponse.json(TWO_BOARDS)),
    http.get(`${API}/schedules/active/page`, () =>
      HttpResponse.json({
        page_id: "page-1",
        source: "schedule",
        schedule_enabled: true,
        temporary_override: override(),
      }),
    ),
    http.get(`${API}/v1/boards/:board`, ({ params }) =>
      HttpResponse.json({
        id: String(params.board),
        name: "Office board",
        override_expires_at: override().expires_at,
        override_started_at: override().started_at,
        // Deliberately "schedule": the UI must still drop the chip while an
        // override runs (H2 normally says override_ends then).
        next_change_at: nineLater,
        next_change_reason: "schedule",
        next_page_id: "page-1",
      }),
    ),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("Cancel override and Undo on a multi-display install", () => {
  it("cancel and Undo both name the selected display, and Undo keeps the revert page", async () => {
    serveOfficeOverride();
    const deletes: (string | null)[] = [];
    const posts: Record<string, unknown>[] = [];
    let current: unknown = { active: false };
    server.use(
      http.delete(`${API}/settings/temporary-override`, ({ request }) => {
        deletes.push(new URL(request.url).searchParams.get("board_id"));
        return HttpResponse.json({ revert_mode: "page" });
      }),
      http.get(`${API}/settings/temporary-override`, () => HttpResponse.json(current as Record<string, unknown>)),
      http.post(`${API}/settings/temporary-override`, async ({ request }) => {
        posts.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json({ active: true });
      }),
    );
    localStorage.setItem("fiestaboard_current_board", "board-2");
    render(<ActivePageDisplay />, { wrapper: Wrapper });

    await screen.findByRole("region", { name: /Now showing.*Office board/ });
    fireEvent.click(await screen.findByRole("button", { name: "Cancel override" }));
    await waitFor(() => expect(deletes).toEqual(["board-2"]));

    await waitFor(() => expect(toast.info).toHaveBeenCalled());
    const options = vi.mocked(toast.info).mock.calls[0][1] as unknown as { action: { onClick: () => Promise<void> } };
    await act(async () => {
      await options.action.onClick();
    });
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toMatchObject({
      board_id: "board-2",
      page_id: "page-2",
      revert_mode: "page",
      revert_page_id: "page-1",
    });
    current = { active: true };
  });

  it("Undo does not overwrite a newer override on that display (S2)", async () => {
    serveOfficeOverride();
    const posts: unknown[] = [];
    server.use(
      http.delete(`${API}/settings/temporary-override`, () => HttpResponse.json({ revert_mode: "schedule" })),
      // Someone set a new hold inside the 10 s window.
      http.get(`${API}/settings/temporary-override`, () => HttpResponse.json({ active: true, page_id: "page-1" })),
      http.post(`${API}/settings/temporary-override`, async ({ request }) => {
        posts.push(await request.json());
        return HttpResponse.json({ active: true });
      }),
    );
    localStorage.setItem("fiestaboard_current_board", "board-2");
    render(<ActivePageDisplay />, { wrapper: Wrapper });
    await screen.findByRole("region", { name: /Now showing.*Office board/ });
    fireEvent.click(await screen.findByRole("button", { name: "Cancel override" }));
    await waitFor(() => expect(toast.info).toHaveBeenCalled());
    const options = vi.mocked(toast.info).mock.calls[0][1] as unknown as { action: { onClick: () => Promise<void> } };
    await act(async () => {
      await options.action.onClick();
    });
    expect(posts).toEqual([]);
    expect(toast.info).toHaveBeenLastCalledWith("A newer Override is on this display now, so it was kept.");
  });
});

describe("the next-change chip while an Override runs", () => {
  it("Change Page from Home offers no Until <time> chip (m24)", async () => {
    serveOfficeOverride();
    let detailServed = false;
    server.use(
      http.get(`${API}/v1/boards/:board`, ({ params }) => {
        detailServed = params.board === "board-2";
        return HttpResponse.json({
          id: String(params.board),
          override_started_at: override().started_at,
          override_expires_at: override().expires_at,
          next_change_at: new Date(Date.now() + 2 * 60 * 60_000).toISOString(),
          next_change_reason: "schedule",
          next_page_id: "page-1",
        });
      }),
    );
    localStorage.setItem("fiestaboard_current_board", "board-2");
    render(<ActivePageDisplay />, { wrapper: Wrapper });
    await screen.findByRole("region", { name: /Now showing.*Office board/ });
    await waitFor(() => expect(detailServed).toBe(true));
    fireEvent.click(await screen.findByRole("button", { name: /^Change Page$/ }));
    const dialog = await screen.findByRole("dialog", { name: "Change Page" });
    fireEvent.click(await within(dialog).findByRole("button", { name: /Weather Page/ }));
    const chips = within(dialog)
      .getAllByRole("radio")
      .map((r) => r.textContent?.trim())
      .filter((label) => label && !["Pages", "Collections"].includes(label));
    expect(chips).toEqual(["15 min", "1 hr", "Until I cancel"]);
  });

  it("Compose offers no Until <time> chip on a display with an Override (m23)", async () => {
    serveOfficeOverride();
    localStorage.setItem("fiestaboard_current_board", "board-2");
    render(<HomeCompose open onOpenChange={vi.fn()} />, { wrapper: Wrapper });
    await screen.findByText("Shows on Office board when you choose Show now. Nothing reaches the board before that.");
    await waitFor(() =>
      expect(screen.getAllByRole("radio").map((r) => r.textContent?.trim())).toEqual([
        "15 min",
        "1 hr",
        "Until I cancel",
      ]),
    );
  });

  it("Compose never sends an indefinite hold after Show on moves to a display whose next change is unknown (M2)", async () => {
    const nine = new Date(Date.now() + 2 * 60 * 60_000).toISOString();
    const posts: Record<string, unknown>[] = [];
    server.use(
      http.get(`${API}/settings/board`, () =>
        HttpResponse.json({
          ...TWO_BOARDS,
          boards: TWO_BOARDS.boards.map((b) => ({ ...b, schedule_enabled: true })),
        }),
      ),
      http.get(`${API}/v1/boards/:board`, ({ params }) =>
        params.board === "board-1"
          ? HttpResponse.json({
              id: "board-1",
              next_change_at: nine,
              next_change_reason: "schedule",
              next_page_id: null,
            })
          : HttpResponse.json({ id: "board-2", next_change_at: null, next_change_reason: null }),
      ),
      http.post(`${API}/settings/temporary-override`, async ({ request }) => {
        posts.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json({ active: true });
      }),
    );
    localStorage.setItem("fiestaboard_current_board", "board-1");
    render(<HomeCompose open onOpenChange={vi.fn()} />, { wrapper: Wrapper });
    const nextChip = await screen.findByRole("radio", { name: /^Until \d/ });
    await waitFor(() => expect(nextChip).toHaveAttribute("aria-checked", "true"));

    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox", { name: "Show on" }));
    await user.click(await screen.findByRole("option", { name: /Office board/ }));
    await screen.findByText("Shows on Office board when you choose Show now. Nothing reaches the board before that.");
    fireEvent.change(screen.getByRole("textbox", { name: /^Message$/ }), { target: { value: "HELLO" } });
    await waitFor(() => expect(screen.getByRole("button", { name: "Show now" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Show now" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toMatchObject({ board_id: "board-2", duration_minutes: 60 });
  });
});

describe("Home keys and the alert name", () => {
  it("ignores Shift+C and keys pressed while a dialog is open (m21, m22)", async () => {
    const onCompose = vi.fn();
    render(<ActivePageDisplay onCompose={onCompose} />, { wrapper: Wrapper });
    await screen.findByTestId("now-showing");
    fireEvent.keyDown(window, { key: "C", shiftKey: true });
    expect(onCompose).not.toHaveBeenCalled();

    const outside = document.createElement("div");
    outside.setAttribute("role", "dialog");
    document.body.appendChild(outside);
    fireEvent.keyDown(window, { key: "c" });
    expect(onCompose).not.toHaveBeenCalled();
    outside.remove();

    fireEvent.keyDown(window, { key: "c" });
    expect(onCompose).toHaveBeenCalledTimes(1);
  });

  it("names the alert by the plugin's display name (S4)", async () => {
    server.use(
      http.get(`${API}/schedules/active/page`, () =>
        HttpResponse.json({
          page_id: "page-1",
          source: "manual",
          schedule_enabled: false,
          temporary_override: override(),
        }),
      ),
      http.get(`${API}/triggers/active`, () =>
        HttpResponse.json({
          trigger: {
            trigger_id: "t1",
            plugin_id: "ring_doorbell",
            priority: 1,
            duration_seconds: 60,
            activated_at: new Date().toISOString(),
            remaining_seconds: 40,
          },
        }),
      ),
      http.get(`${API}/plugins`, () =>
        HttpResponse.json({ plugins: [{ id: "ring_doorbell", name: "Ring Doorbell" }], total: 1 }),
      ),
    );
    render(<ActivePageDisplay />, { wrapper: Wrapper });
    expect(await screen.findByRole("heading", { level: 2, name: "Alert from Ring Doorbell" })).toBeInTheDocument();
  });
});
