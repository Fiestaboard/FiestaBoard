/**
 * The page's one status banner (slice 2.3, WEB-10; 07a `Web / Banner`
 * `298:2280`), wired to real hub state: `GET /v1/status` (paused, H12
 * health, init errors, reachability), `GET /silence-status`, the browser's
 * network, and for a FiestaPanel the signed-in TVs' last shows (H13b).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { CONNECTION_HELP_URL, StatusBannerHost } from "@/components/status-banners/status-banner-host";

import { server } from "./mocks/server";

const API = "/api";

const HEALTHY = {
  last_connected_at: "2026-11-13T22:00:00+00:00",
  last_update_at: "2026-11-13T22:00:00+00:00",
  latency_ms: 40,
  last_error_at: null,
  last_error: null,
  reachable: true,
  breaker_open: false,
};

type BoardStatus = Record<string, unknown>;

function boardStatus(overrides: BoardStatus = {}): BoardStatus {
  return { configured: true, paused: false, active_page_id: null, health: HEALTHY, ...overrides };
}

function setup({
  status = { kitchen: boardStatus() },
  boards = [{ id: "kitchen", name: "Kitchen board", device_type: "flagship", board_color: "black" }],
  silence = { enabled: false, active: false },
  statusResponse,
}: {
  status?: Record<string, BoardStatus>;
  boards?: Record<string, unknown>[];
  silence?: Record<string, unknown>;
  statusResponse?: () => Response;
} = {}) {
  server.use(
    http.get(`${API}/settings/board`, () => HttpResponse.json({ board_type: "black", boards, devices: ["flagship"] })),
    http.get(`${API}/v1/status`, () =>
      statusResponse
        ? statusResponse()
        : HttpResponse.json({ running: true, initialized: true, config_summary: {}, boards: status }),
    ),
    http.get(`${API}/silence-status`, () =>
      HttpResponse.json({
        start_time_utc: "",
        end_time_utc: "",
        current_time_utc: "",
        next_change_utc: "",
        ...silence,
      }),
    ),
    http.get(`${API}/v1/pages`, () =>
      HttpResponse.json({
        pages: [
          { id: "commute", name: "Evening commute" },
          { id: "night", name: "Good night" },
        ],
      }),
    ),
  );
}

function Wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <CurrentBoardProvider>{children}</CurrentBoardProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

function setOnline(value: boolean) {
  Object.defineProperty(window.navigator, "onLine", { configurable: true, get: () => value });
}

afterEach(() => {
  setOnline(true);
});

async function settle() {
  // Let the status, board and silence queries land.
  await new Promise((r) => setTimeout(r, 50));
}

describe("StatusBannerHost", () => {
  it("shows no banner while everything is healthy", async () => {
    setup();
    render(<StatusBannerHost />, { wrapper: Wrapper });
    await settle();
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
  });

  it("says a display is offline, when it was last connected, and links Diagnostics", async () => {
    setup({
      status: {
        kitchen: boardStatus({
          paused: true,
          health: { ...HEALTHY, reachable: false, last_error: "unreachable", last_error_at: "2026-11-13T22:05:00Z" },
        }),
      },
    });
    render(<StatusBannerHost />, { wrapper: Wrapper });

    const banner = await screen.findByRole("group", { name: "Kitchen board is offline" });
    expect(banner).toHaveAttribute("data-kind", "display-offline");
    expect(banner).toHaveTextContent("Last connected");
    expect(banner).toHaveTextContent("FiestaBoard checks again on its own");
    expect(screen.getByRole("link", { name: "Diagnostics" })).toHaveAttribute(
      "href",
      "/displays/kitchen?section=settings",
    );
  });

  it("says a paused display keeps showing its page, and Resume un-pauses it", async () => {
    let patched: unknown = null;
    setup({ status: { kitchen: boardStatus({ paused: true, active_page_id: "commute" }) } });
    server.use(
      http.patch(`${API}/v1/boards/kitchen`, async ({ request }) => {
        patched = await request.json();
        return HttpResponse.json({ id: "kitchen", paused: false });
      }),
    );
    render(<StatusBannerHost />, { wrapper: Wrapper });

    const banner = await screen.findByRole("group", { name: "Kitchen board is paused" });
    await waitFor(() =>
      expect(banner).toHaveTextContent("It keeps showing Evening commute and skips the Schedule until you resume it."),
    );
    await userEvent.setup().click(screen.getByRole("button", { name: "Resume" }));
    await waitFor(() => expect(patched).toEqual({ paused: false }));
  });

  it("shows a Silence Schedule with when it ends and the page it holds, with no action", async () => {
    setup({
      silence: {
        enabled: true,
        active: true,
        mode: "page",
        page_id: "night",
        ends_at_utc: "2026-11-14T14:30:00Z",
      },
    });
    render(<StatusBannerHost />, { wrapper: Wrapper });

    const banner = await screen.findByRole("group", { name: /^Silence Schedule until / });
    expect(banner).toHaveAttribute("data-kind", "silenced");
    await waitFor(() => expect(banner).toHaveTextContent("Kitchen board stays on Good night"));
    expect(banner.querySelector('[data-slot="status-banner-actions"]')).toBeNull();
  });

  it("leaves silenced to the page when the page excludes it", async () => {
    setup({ silence: { enabled: true, active: true, mode: "freeze", ends_at_utc: "2026-11-14T14:30:00Z" } });
    render(<StatusBannerHost exclude={["silenced"]} />, { wrapper: Wrapper });
    await settle();
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
  });

  it("says the hub can't be reached when the status poll gets no answer, and Try again asks again", async () => {
    let calls = 0;
    setup({
      statusResponse: () => {
        calls += 1;
        return HttpResponse.error();
      },
    });
    render(<StatusBannerHost />, { wrapper: Wrapper });

    const banner = await screen.findByRole("group", { name: `Can't reach your hub at ${window.location.hostname}` });
    expect(banner).toHaveAttribute("data-kind", "hub-unreachable");
    expect(banner).toHaveTextContent("Your displays keep running their schedules on the hub");
    // It never answered this page, so there is no "Last connected" time to quote.
    expect(banner).toHaveTextContent("Trying again every 15 s.");
    expect(banner).not.toHaveTextContent("Last connected");
    const help = screen.getByRole("link", { name: /Connection help/ });
    expect(help).toHaveAttribute("href", CONNECTION_HELP_URL);
    expect(help).toHaveAttribute("target", "_blank");

    const before = calls;
    await userEvent.setup().click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(calls).toBeGreaterThan(before));
  });

  it("quotes when the hub last answered once it stops answering", async () => {
    let fail = false;
    setup({
      statusResponse: () =>
        fail
          ? HttpResponse.error()
          : HttpResponse.json({ running: true, initialized: true, config_summary: {}, boards: {} }),
    });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={queryClient}>
          <CurrentBoardProvider>
            <StatusBannerHost />
          </CurrentBoardProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    );
    await settle();
    expect(screen.queryByRole("group")).not.toBeInTheDocument();

    fail = true;
    await queryClient.refetchQueries({ queryKey: ["status"] }).catch(() => {});
    const banner = await screen.findByRole("group", { name: /^Can't reach your hub at / }, { timeout: 3000 });
    expect(banner).toHaveTextContent(/Last connected .+ · trying again every 15 s\./);
  });

  it("treats an HTTP answer from the hub (a 503 while it starts) as reachable", async () => {
    setup({ statusResponse: () => HttpResponse.json({ detail: "Service not initialized" }, { status: 503 }) });
    render(<StatusBannerHost />, { wrapper: Wrapper });
    await settle();
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
  });

  it("says this device is offline ahead of everything else", async () => {
    setOnline(false);
    setup({ status: { kitchen: boardStatus({ paused: true }) } });
    render(<StatusBannerHost />, { wrapper: Wrapper });

    const banner = await screen.findByRole("group", { name: "You're offline" });
    expect(banner).toHaveTextContent("This computer has no network.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: /paused/ })).not.toBeInTheDocument();
  });

  it("names the TV that last showed a FiestaPanel when no TV shows it now, and Check again re-reads", async () => {
    let sessionReads = 0;
    setup({
      boards: [{ id: "living", name: "Living room TV", device_type: "panel", output: "fiestapanel" }],
      status: { living: boardStatus({ health: { ...HEALTHY, reachable: null } }) },
    });
    const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
    server.use(
      http.get(`${API}/panels`, () =>
        HttpResponse.json({ panels: [{ id: "p1", board_id: "living", name: "Living room TV", is_display: false }] }),
      ),
      http.get(`${API}/auth/sessions`, () => {
        sessionReads += 1;
        return HttpResponse.json({
          current_session_id: "me",
          sessions: [
            { id: "me", kind: "browser", device_name: "Chrome on macOS", shown_panels: [] },
            {
              id: "tv1",
              kind: "tv",
              device_name: "Apple TV",
              shown_panels: [{ panel_id: "p1", last_shown_at: twoHoursAgo }],
            },
          ],
        });
      }),
    );
    render(<StatusBannerHost />, { wrapper: Wrapper });

    const banner = await screen.findByRole("group", { name: "No TV is showing Living room TV" });
    expect(banner).toHaveAttribute("data-kind", "no-viewer");
    expect(banner).toHaveTextContent("Last shown on Apple TV · 2 hours ago");
    const before = sessionReads;
    await userEvent.setup().click(screen.getByRole("button", { name: "Check again" }));
    await waitFor(() => expect(sessionReads).toBeGreaterThan(before));
  });

  it("shows no viewer banner when the TV list can't be read (sign-in off)", async () => {
    setup({
      boards: [{ id: "living", name: "Living room TV", device_type: "panel", output: "fiestapanel" }],
      status: { living: boardStatus({ health: { ...HEALTHY, reachable: null } }) },
    });
    server.use(
      http.get(`${API}/panels`, () =>
        HttpResponse.json({ panels: [{ id: "p1", board_id: "living", name: "Living room TV", is_display: false }] }),
      ),
      http.get(`${API}/auth/sessions`, () => HttpResponse.json({ error: "unauthorized" }, { status: 401 })),
    );
    render(<StatusBannerHost />, { wrapper: Wrapper });
    await settle();
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
  });

  it("on Home (fleet) also names every display that failed to start", async () => {
    setup({
      boards: [
        { id: "kitchen", name: "Kitchen board", device_type: "flagship" },
        { id: "pixoo", name: "Desk Pixoo", device_type: "flagship" },
      ],
      status: { kitchen: boardStatus(), pixoo: boardStatus({ configured: false, error: "Couldn't connect" }) },
    });
    render(<StatusBannerHost fleet />, { wrapper: Wrapper });

    expect(await screen.findByRole("group", { name: "Couldn't start Desk Pixoo" })).toHaveAttribute(
      "data-kind",
      "init-error",
    );
  });

  it("is about the board it is given, not the current one", async () => {
    setup({
      boards: [
        { id: "kitchen", name: "Kitchen board", device_type: "flagship" },
        { id: "clock", name: "Entry clock", device_type: "flagship" },
      ],
      status: {
        kitchen: boardStatus(),
        clock: boardStatus({ health: { ...HEALTHY, reachable: false, last_connected_at: null } }),
      },
    });
    render(<StatusBannerHost boardId="clock" />, { wrapper: Wrapper });

    const banner = await screen.findByRole("group", { name: "Entry clock is offline" });
    expect(banner).toHaveTextContent("The hub hasn't reached it since it started.");
  });
});
