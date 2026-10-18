// ActivePageDisplay shows the Moon "Silence mode active" badge when silence is
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
      expect(screen.queryByText("Silence mode active")).not.toBeInTheDocument();
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

    await waitFor(() => expect(screen.getByText("Silence mode active")).toBeInTheDocument());
  });

  it("shows silence badge when active and mode === 'freeze'", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () => HttpResponse.json(silenceStatus({ active: true, mode: "freeze" }))),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => expect(screen.getByText("Silence mode active")).toBeInTheDocument());
  });

  it("shows silence badge when active and mode === 'page'", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json(silenceStatus({ active: true, mode: "page", page_id: "page-night" })),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => expect(screen.getByText("Silence mode active")).toBeInTheDocument());
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

    // The silence page is named and linked to its editor.
    const silenceLink = await screen.findByRole("link", { name: 'Edit page "Custom Template"' });
    expect(silenceLink).toHaveAttribute("href", "/pages/edit/page-2");

    // The manual/scheduled page it replaced is NOT shown.
    expect(screen.queryByRole("link", { name: 'Edit page "Weather Page"' })).not.toBeInTheDocument();
  });

  it("keeps the normal active page when silence is active but mode !== 'page'", async () => {
    // Regression guard: freeze/indicator modes must not hijack the header.
    server.use(
      http.get(`${API_BASE}/silence-status`, () => HttpResponse.json(silenceStatus({ active: true, mode: "freeze" }))),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    const activeLink = await screen.findByRole("link", { name: 'Edit page "Weather Page"' });
    expect(activeLink).toHaveAttribute("href", "/pages/edit/page-1");
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

    await waitFor(() => expect(screen.getByText("Silence mode active")).toBeInTheDocument());
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

describe("ActivePageDisplay - silence alert (#1943, #1944)", () => {
  afterEach(() => {
    server.resetHandlers();
    vi.restoreAllMocks();
  });

  it("says when silence ends and which page shows then (manual mode)", async () => {
    serveSilence(silenced());
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    const alert = await screen.findByTestId("silence-alert");
    expect(alert).toHaveTextContent(`Silenced until ${localTime(ENDS_AT)}`);
    await waitFor(() =>
      expect(alert).toHaveTextContent("“Weather Page” will show when silence ends. The board stays quiet until then."),
    );
    expect(screen.getByTestId("silence-show-now")).toBeInTheDocument();
    expect(screen.queryByTestId("silence-discard-held")).not.toBeInTheDocument();
  });

  it("says the schedule resumes in schedule mode, with no Show now", async () => {
    serveSilence(silenced());
    server.use(
      http.get(`${API_BASE}/schedules/active/page`, () =>
        HttpResponse.json({
          page_id: "page-1",
          source: "schedule",
          schedule_enabled: true,
          temporary_override: { active: false },
        }),
      ),
    );
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    const alert = await screen.findByTestId("silence-alert");
    await waitFor(() => expect(alert).toHaveTextContent("Your schedule resumes when silence ends."));
    expect(screen.queryByTestId("silence-show-now")).not.toBeInTheDocument();
  });

  it("names a collection but offers no Show now for it", async () => {
    serveSilence(silenced());
    server.use(
      http.get(`${API_BASE}/settings/active-page`, () =>
        HttpResponse.json({ page_id: "collection:mornings", resolved_page_id: "page-1", board_id: null }),
      ),
      http.get(`${API_BASE}/v1/collections`, () =>
        HttpResponse.json({
          collections: [{ id: "collection:mornings", name: "Mornings", page_ids: ["page-1"], mode: "rotate" }],
          total: 1,
        }),
      ),
    );
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    const alert = await screen.findByTestId("silence-alert");
    await waitFor(() => expect(alert).toHaveTextContent("“Mornings” will show when silence ends."));
    expect(screen.queryByTestId("silence-show-now")).not.toBeInTheDocument();
  });

  it("says only that the board stays quiet when no page is selected", async () => {
    serveSilence(silenced());
    server.use(
      http.get(`${API_BASE}/settings/active-page`, () =>
        HttpResponse.json({ page_id: null, resolved_page_id: null, board_id: null }),
      ),
      http.get(`${API_BASE}/schedules/active/page`, () =>
        HttpResponse.json({ page_id: null, source: "manual", schedule_enabled: false, temporary_override: null }),
      ),
      http.get(`${API_BASE}/v1/pages`, () => HttpResponse.json({ pages: [], total: 0 })),
    );
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    const alert = await screen.findByTestId("silence-alert");
    expect(alert).toHaveTextContent("The board stays quiet until then.");
    expect(alert).not.toHaveTextContent("will show when silence ends");
  });

  it("hides the 'changed by another app' warning while silenced, since Restore cannot send", async () => {
    serveSilence(silenced());
    server.use(
      http.get(`${API_BASE}/board/current-message`, () =>
        HttpResponse.json({
          characters: Array.from({ length: 6 }, () => Array(22).fill(1)),
          message: "",
          rows: 6,
          cols: 22,
          expected_characters: Array.from({ length: 6 }, () => Array(22).fill(2)),
          cached_at: null,
          api_mode: "local",
        }),
      ),
    );
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => expect(screen.getByTestId("silence-alert")).toBeInTheDocument());
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByTestId("board-out-of-sync")).not.toBeInTheDocument();
  });

  it("shows nothing when the board is not silenced", async () => {
    serveSilence(silenceStatus({ active: false }));
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    await screen.findByRole("link", { name: 'Edit page "Weather Page"' });
    expect(screen.queryByTestId("silence-alert")).not.toBeInTheDocument();
  });

  it("shows the held message first, and Discard deletes it and refreshes the status", async () => {
    const calls = { count: 0 };
    serveSilence(
      silenced({
        holds_blocked_sends: true,
        held: { kind: "text", preview: "GOOD MORNING EVERYONE HAVE A…", queued_at: "2026-05-04T09:00:00+00:00" },
      }),
      calls,
    );
    let deleted: string | null = null;
    server.use(
      http.delete(`${API_BASE}/silence-queue`, ({ request }) => {
        deleted = request.url;
        return HttpResponse.json({ board_id: "default", discarded: true });
      }),
    );
    const success = vi.spyOn((await import("sonner")).toast, "success");
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    expect(await screen.findByTestId("silence-held")).toHaveTextContent(
      "Held message: “GOOD MORNING EVERYONE HAVE A…” — it shows first.",
    );
    const before = calls.count;
    await user.click(screen.getByTestId("silence-discard-held"));

    await waitFor(() => expect(deleted).not.toBeNull());
    await waitFor(() => expect(success).toHaveBeenCalledWith("Held message discarded"));
    await waitFor(() => expect(calls.count).toBeGreaterThan(before));
  });

  it("Show now re-sends the active page with override_silence and says so", async () => {
    serveSilence(silenced());
    const bodies = capturePicks();
    const success = vi.spyOn((await import("sonner")).toast, "success");
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await user.click(await screen.findByTestId("silence-show-now"));

    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({ page_id: "page-1", override_silence: true });
    await waitFor(() => expect(success).toHaveBeenCalledWith("Showing “Weather Page” now"));
  });
});

describe("ActivePageDisplay - picking a page during silence (#1943)", () => {
  afterEach(() => {
    server.resetHandlers();
    vi.restoreAllMocks();
  });

  async function pickCustomTemplate(user: ReturnType<typeof userEvent.setup>) {
    await user.click((await screen.findAllByRole("button", { name: /change page/i }))[0]);
    const option = await screen.findByRole("button", { name: /custom template/i }, { timeout: 4000 });
    await user.click(option);
  }

  it("the Change Page sheet says the pick is saved, not shown", async () => {
    serveSilence(silenced());
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    await user.click((await screen.findAllByRole("button", { name: /change page/i }))[0]);
    expect(await screen.findByTestId("select-page-silence")).toHaveTextContent(
      "the page you pick is saved and shows then. The board stays quiet.",
    );
  });

  it("the sheet carries no silence note when the board is not silenced", async () => {
    serveSilence(silenceStatus({ active: false }));
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    await user.click((await screen.findAllByRole("button", { name: /change page/i }))[0]);
    await screen.findByText("Select Page");
    expect(screen.queryByTestId("select-page-silence")).not.toBeInTheDocument();
  });

  it("a held pick is sent WITHOUT override and the toast offers Show now, which overrides", async () => {
    serveSilence(silenced());
    const bodies = capturePicks();
    const info = vi.spyOn((await import("sonner")).toast, "info");
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await pickCustomTemplate(user);

    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toEqual({ page_id: "page-2" });
    await waitFor(() => expect(info).toHaveBeenCalled());
    const [message, options] = info.mock.calls[0] as [string, { action: { label: string; onClick: () => void } }];
    expect(message).toBe(`“Custom Template” will show at ${localTime(ENDS_AT)}`);
    expect(options.action.label).toBe("Show now");

    options.action.onClick();
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toEqual({ page_id: "page-2", override_silence: true });
  });

  it("a paused board's pick says it shows when you resume", async () => {
    serveSilence(silenced());
    capturePicks({ paused: true, silenced: true, sent_to_board: false });
    const info = vi.spyOn((await import("sonner")).toast, "info");
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await pickCustomTemplate(user);

    await waitFor(() =>
      expect(info).toHaveBeenCalledWith("Saved — “Custom Template” will show when you resume the board"),
    );
  });
});
