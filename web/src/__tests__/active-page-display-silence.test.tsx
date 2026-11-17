// ActivePageDisplay shows the Moon "Silenced" badge when silence is
// active (regardless of mode). The old snoozing indicator overlay was removed
// when Active Display was refactored to show the polled board state directly.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const API_BASE = "/api";

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
}));

vi.mock("@/components/smart-link", () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

import { ActivePageDisplay } from "@/components/active-page-display";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return (
    <QueryClientProvider client={queryClient}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          {children}
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}

function silenceStatus(overrides: Record<string, unknown>) {
  return {
    enabled: true,
    active: false,
    start_time_utc: "04:00+00:00",
    end_time_utc: "15:00+00:00",
    current_time_utc: "2026-05-04T10:00:00+00:00",
    next_change_utc: "2026-05-04T15:00:00+00:00",
    mode: "freeze",
    page_id: null,
    indicator_text: "SNOOZING",
    indicator_position: "center",
    ...overrides,
  };
}

describe("ActivePageDisplay - silence overlay visibility", () => {
  afterEach(() => {
    server.resetHandlers();
  });

  it("does NOT show silence badge when silence is inactive", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json(silenceStatus({ active: false, mode: "indicator" })),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    await waitFor(() => {
      expect(screen.queryByText("Silenced")).not.toBeInTheDocument();
    });
  });

  it("shows silence badge when active AND mode === 'indicator'", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json(
          silenceStatus({
            active: true,
            mode: "indicator",
            indicator_text: "BEDTIME",
            indicator_position: "bottom-right",
          }),
        ),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => expect(screen.getByText("Silenced")).toBeInTheDocument());
  });

  it("shows silence badge when active and mode === 'freeze'", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () => HttpResponse.json(silenceStatus({ active: true, mode: "freeze" }))),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => expect(screen.getByText("Silenced")).toBeInTheDocument());
  });

  it("shows silence badge when active and mode === 'page'", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json(silenceStatus({ active: true, mode: "page", page_id: "page-night" })),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => expect(screen.getByText("Silenced")).toBeInTheDocument());
  });

  it("names and links the configured silence page when mode === 'page' (issue #1637)", async () => {
    // Manual mode keeps page-1 ("Weather Page") active, but silence "page"
    // mode freezes the board on page-2 ("Custom Template"). The header must
    // follow the board, not the overridden manual page.
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json(silenceStatus({ active: true, mode: "page", page_id: "page-2" })),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    // The silence page is the card's title, and Edit page opens it.
    expect(await screen.findByRole("heading", { level: 2, name: "Custom Template" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Edit page" })).toHaveAttribute("href", "/pages/edit/page-2");

    // The manual/scheduled page it replaced is NOT shown.
    expect(screen.queryByRole("heading", { level: 2, name: "Weather Page" })).not.toBeInTheDocument();
  });

  it("keeps the normal active page when silence is active but mode !== 'page'", async () => {
    // Regression guard: freeze/indicator modes must not hijack the header.
    server.use(
      http.get(`${API_BASE}/silence-status`, () => HttpResponse.json(silenceStatus({ active: true, mode: "freeze" }))),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    expect(await screen.findByRole("heading", { level: 2, name: "Weather Page" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Edit page" })).toHaveAttribute("href", "/pages/edit/page-1");
  });

  it("shows silence badge even when indicator_text/position are missing", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json({
          enabled: true,
          active: true,
          start_time_utc: "04:00+00:00",
          end_time_utc: "15:00+00:00",
          current_time_utc: "2026-05-04T10:00:00+00:00",
          next_change_utc: "2026-05-04T15:00:00+00:00",
          mode: "indicator",
          page_id: null,
          // indicator_text and indicator_position omitted
        }),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => expect(screen.getByText("Silenced")).toBeInTheDocument());
  });
});

// ---------------------------------------------------------------------------
// #1943 / #1944 — hold by default, one explicit "Show now", held messages
// ---------------------------------------------------------------------------

const ENDS_AT = "2026-05-04T15:00:00+00:00";
const localTime = (iso: string) => new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });

function silenced(overrides: Record<string, unknown> = {}) {
  return silenceStatus({
    active: true,
    mode: "freeze",
    ends_at_utc: ENDS_AT,
    seconds_until_next_change: 3600,
    holds_blocked_sends: false,
    held: null,
    ...overrides,
  });
}

function serveSilence(status: Record<string, unknown>, calls?: { count: number }) {
  server.use(
    http.get(`${API_BASE}/silence-status`, () => {
      if (calls) calls.count += 1;
      return HttpResponse.json(status);
    }),
  );
}

/** Capture every PUT /settings/active-page body, answering with `answer`. */
function capturePicks(answer: Record<string, unknown> = {}) {
  const bodies: Record<string, unknown>[] = [];
  server.use(
    http.put(`${API_BASE}/settings/active-page`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      bodies.push(body);
      const overriding = body.override_silence === true;
      return HttpResponse.json({
        page_id: body.page_id,
        sent_to_board: overriding,
        paused: false,
        silenced: !overriding,
        board_id: null,
        error: null,
        warnings: [],
        ...answer,
      });
    }),
  );
  return bodies;
}

describe("ActivePageDisplay - silence hand-off (2.3b)", () => {
  afterEach(() => {
    server.resetHandlers();
    vi.restoreAllMocks();
  });
  it("keeps only the Silenced badge; the route owns the standing notice", async () => {
    serveSilence(silenced());
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    await screen.findByText("Silenced");
    expect(screen.queryByTestId("silence-alert")).not.toBeInTheDocument();
    expect(screen.queryByTestId("silence-show-now")).not.toBeInTheDocument();
    expect(screen.queryByTestId("home-held-message")).not.toBeInTheDocument();
  });
  it("suppresses another-app recovery while silenced", async () => {
    serveSilence(silenced());
    server.use(
      http.get(`${API_BASE}/board/current-message`, () =>
        HttpResponse.json({ characters: [[1]], expected_characters: [[2]], message: "", rows: 6, cols: 22 }),
      ),
    );
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    await screen.findByText("Silenced");
    expect(screen.queryByTestId("board-out-of-sync")).not.toBeInTheDocument();
  });
  it("keeps the held message and Discard refreshes its status", async () => {
    const calls = { count: 0 };
    serveSilence(
      silenced({
        holds_blocked_sends: true,
        held: { kind: "text", preview: "GOOD LUCK", queued_at: "2026-05-04T09:00:00Z" },
      }),
      calls,
    );
    let deleted = false;
    server.use(
      http.delete(`${API_BASE}/silence-queue`, () => {
        deleted = true;
        return HttpResponse.json({ discarded: true });
      }),
    );
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    expect(await screen.findByTestId("home-held-message")).toHaveTextContent("GOOD LUCK");
    const before = calls.count;
    await user.click(screen.getByRole("button", { name: "Discard" }));
    await waitFor(() => expect(deleted).toBe(true));
    await waitFor(() => expect(calls.count).toBeGreaterThan(before));
    expect(screen.queryByTestId("silence-show-now")).not.toBeInTheDocument();
  });
});

describe("ActivePageDisplay - Change Page during silence (#1943, 2.2)", () => {
  afterEach(() => {
    server.resetHandlers();
    vi.restoreAllMocks();
  });

  // CANON's Change Page ends in Show now, which shows the page right away:
  // during silence it wakes the board, and the dialog says so before the tap.
  async function pickCustomTemplate(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByRole("button", { name: /^Change Page$/ }));
    await user.click(await screen.findByRole("button", { name: /Custom Template/ }));
    await user.click(screen.getByRole("button", { name: "Show now" }));
  }

  it("the Change Page dialog says Show now wakes the silenced display", async () => {
    serveSilence(silenced());
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    await user.click(await screen.findByRole("button", { name: /^Change Page$/ }));
    expect(await screen.findByTestId("change-page-silence")).toHaveTextContent(
      "Show now wakes Flagship from its Silence Schedule.",
    );
  });

  it("the dialog carries no silence note when the board is not silenced", async () => {
    serveSilence(silenceStatus({ active: false }));
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    await user.click(await screen.findByRole("button", { name: /^Change Page$/ }));
    await screen.findByRole("dialog", { name: "Change Page" });
    expect(screen.queryByTestId("change-page-silence")).not.toBeInTheDocument();
  });

  it("a Manual Mode pick during silence is shown now, with override_silence", async () => {
    serveSilence(silenced());
    const bodies = capturePicks();
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await pickCustomTemplate(user);

    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toEqual({ page_id: "page-2", board_id: "default", override_silence: true });
  });

  it("a paused board's pick says it shows when you resume", async () => {
    serveSilence(silenced());
    capturePicks({ paused: true, silenced: true, sent_to_board: false });
    const info = vi.spyOn((await import("sonner")).toast, "info");
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await pickCustomTemplate(user);

    await waitFor(() => expect(info).toHaveBeenCalledWith("Saved. Custom Template shows when you resume Flagship."));
  });
});
