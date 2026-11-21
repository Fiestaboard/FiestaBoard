// Home's Now showing card (slice 2.2, 07a §3): mode badge, the Override
// countdown and outcome sentence, Cancel override with Undo, the trigger
// carry (an alert covers the override), Change Page and the C / P keys.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { toast } from "sonner";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const API_BASE = "/api";

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
    toast: Object.assign(vi.fn(), {
      success: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
      warning: vi.fn(),
      dismiss: vi.fn(),
    }),
  };
});

import { ActivePageDisplay } from "@/components/active-page-display";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
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

const inactive = {
  active: false,
  page_id: null,
  expires_at: null,
  remaining_seconds: null,
  revert_mode: null,
  revert_page_id: null,
};

function activeSchedule(overrides: Record<string, unknown> = {}) {
  return { page_id: "page-1", source: "manual", schedule_enabled: false, temporary_override: inactive, ...overrides };
}

function override(remainingSeconds: number | null = 300, extra: Record<string, unknown> = {}) {
  return {
    active: true,
    page_id: "page-2",
    expires_at: remainingSeconds === null ? null : new Date(Date.now() + remainingSeconds * 1000).toISOString(),
    started_at: new Date(Date.now() - 60_000).toISOString(),
    remaining_seconds: remainingSeconds,
    revert_mode: "schedule",
    revert_page_id: null,
    ...extra,
  };
}

function boardDetail(extra: Record<string, unknown> = {}) {
  return {
    id: "default",
    name: "Flagship",
    device_type: "flagship",
    rows: 6,
    cols: 22,
    is_primary: true,
    paused: false,
    schedule_enabled: false,
    auto_restore: true,
    output: "vestaboard",
    characters: null,
    text: null,
    read_at: null,
    active_page_id: "page-1",
    scheduled_page_id: null,
    resolved_page_id: "page-1",
    source: "manual",
    default_page_id: null,
    override_expires_at: null,
    next_change_at: null,
    next_change_reason: null,
    next_page_id: null,
    ...extra,
  };
}

function useSchedule(schedule: Record<string, unknown>, detail: Record<string, unknown> = {}) {
  server.use(
    http.get(`${API_BASE}/schedules/active/page`, () => HttpResponse.json(activeSchedule(schedule))),
    http.get(`${API_BASE}/v1/boards/:board`, () => HttpResponse.json(boardDetail(detail))),
  );
}

afterEach(() => {
  server.resetHandlers();
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

describe("ActivePageDisplay - Now showing", () => {
  it("names the display in the card header and shows Manual Mode with its sentence", async () => {
    useSchedule({});
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    const card = await screen.findByTestId("now-showing");
    await within(card).findByText("Manual Mode");
    expect(within(card).getByRole("heading", { level: 2, name: "Weather Page" })).toBeInTheDocument();
    expect(
      within(card).getByText("Schedule Mode is off · Weather Page stays until you change it."),
    ).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: /Edit page/ })).toHaveAttribute("href", "/pages/edit/page-1");
  });

  it("in Schedule Mode says when the next change is and what follows (H2), with View Schedule", async () => {
    const at = new Date(Date.now() + 2 * 60 * 60_000);
    useSchedule(
      { schedule_enabled: true, source: "schedule" },
      { next_change_at: at.toISOString(), next_change_reason: "schedule", next_page_id: "page-2" },
    );
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    const card = await screen.findByTestId("now-showing");
    await within(card).findByText("Schedule Mode");
    const time = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(at);
    expect(
      await within(card).findByText(
        `Until ${time} · then Custom Template. Schedule Mode keeps running; nothing needs you.`,
      ),
    ).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: /View Schedule/ })).toHaveAttribute("href", "/schedule");
  });

  it("shows the Override badge, the override's page, the countdown and the outcome", async () => {
    useSchedule({ temporary_override: override(42 * 60) });
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    const card = await screen.findByTestId("now-showing");
    await within(card).findByText("Override");
    expect(within(card).getByRole("heading", { level: 2, name: "Custom Template" })).toBeInTheDocument();
    expect(within(card).getByRole("timer")).toHaveTextContent("42m left");
    expect(within(card).getByText(/^Holds until .+, then Weather Page comes back\.$/)).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Cancel override" })).toBeInTheDocument();
  });

  it("says an override with no end holds until it is canceled, with no countdown", async () => {
    useSchedule({ temporary_override: override(null) });
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    const card = await screen.findByTestId("now-showing");
    await within(card).findByText("Holds until you cancel or Change Page again.");
    expect(within(card).queryByRole("timer")).not.toBeInTheDocument();
  });

  it("names a composed message, which has no page to edit", async () => {
    useSchedule({ temporary_override: override(300, { page_id: null, template: ["DINNER AT 7"] }) });
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    const card = await screen.findByTestId("now-showing");
    expect(await within(card).findByRole("heading", { level: 2, name: "Composed message" })).toBeInTheDocument();
    expect(within(card).queryByRole("link", { name: /Edit page/ })).not.toBeInTheDocument();
  });

  it("never claims the override is on screen while a plugin trigger shows (H1 carry)", async () => {
    useSchedule({ temporary_override: override(300) });
    server.use(
      http.get(`${API_BASE}/triggers/active`, () =>
        HttpResponse.json({
          trigger: {
            trigger_id: "t1",
            plugin_id: "doorbell",
            priority: 10,
            duration_seconds: 60,
            activated_at: new Date().toISOString(),
            remaining_seconds: 50,
          },
        }),
      ),
    );
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    const card = await screen.findByTestId("now-showing");
    expect(await within(card).findByRole("heading", { level: 2, name: "Alert from doorbell" })).toBeInTheDocument();
    expect(
      within(card).getByText("An alert is on the board. Custom Template comes back when it ends."),
    ).toBeInTheDocument();
    expect(within(card).queryByText("Override")).not.toBeInTheDocument();
    expect(within(card).queryByRole("timer")).not.toBeInTheDocument();
    // The override is still running, so it can still be canceled.
    expect(within(card).getByRole("button", { name: "Cancel override" })).toBeInTheDocument();
  });

  it("starts the out-of-sync sentence cleanly when a trigger leaves no outcome", async () => {
    useSchedule({ temporary_override: override(300) });
    server.use(
      http.get(`${API_BASE}/triggers/active`, () =>
        HttpResponse.json({
          trigger: {
            trigger_id: "t1",
            plugin_id: "doorbell",
            priority: 10,
            duration_seconds: 60,
            activated_at: new Date().toISOString(),
            remaining_seconds: 50,
          },
        }),
      ),
      http.get(`${API_BASE}/board/current-message`, () =>
        HttpResponse.json({ characters: [[1]], expected_characters: [[2]], message: "OTHER", rows: 6, cols: 22 }),
      ),
    );
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    const card = await screen.findByTestId("now-showing");
    // No whitespace normalization: the old join rendered a leading space.
    expect(
      await within(card).findByText(
        "The board itself reports something else; Show Alert from doorbell again re-sends it.",
        { normalizer: (text) => text },
      ),
    ).toBeInTheDocument();
  });

  it("cancels the override and offers Undo, which puts the same hold back", async () => {
    let deletes = 0;
    const posts: unknown[] = [];
    useSchedule({ temporary_override: override(30 * 60) });
    server.use(
      http.delete(`${API_BASE}/settings/temporary-override`, () => {
        deletes += 1;
        return HttpResponse.json({ revert_mode: "schedule" });
      }),
      http.post(`${API_BASE}/settings/temporary-override`, async ({ request }) => {
        posts.push(await request.json());
        return HttpResponse.json({ active: true });
      }),
    );
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    fireEvent.click(await screen.findByRole("button", { name: "Cancel override" }));
    await waitFor(() => expect(deletes).toBe(1));
    await waitFor(() => expect(toast.info).toHaveBeenCalled());
    const [message, options] = vi.mocked(toast.info).mock.calls[0] as [
      string,
      { duration: number; action: { label: string; onClick: () => Promise<void> | void } },
    ];
    expect(message).toBe("Override canceled");
    expect(options.duration).toBe(10_000);
    expect(options.action.label).toBe("Undo");
    await act(async () => {
      await options.action.onClick();
    });
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toMatchObject({ page_id: "page-2", duration_minutes: 30, revert_mode: "schedule" });
  });

  it("refetches the display's state when the countdown ends", async () => {
    let reads = 0;
    server.use(
      http.get(`${API_BASE}/schedules/active/page`, () => {
        reads += 1;
        return HttpResponse.json(activeSchedule({ temporary_override: override(-5) }));
      }),
    );
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    // Past its end at mount: Countdown's onEnd fires once and Home refetches.
    await waitFor(() => expect(reads).toBeGreaterThanOrEqual(2));
  });

  it("opens Change Page from the card and from P; C asks for Compose", async () => {
    useSchedule({});
    const onCompose = vi.fn();
    render(<ActivePageDisplay onCompose={onCompose} />, { wrapper: TestWrapper });
    fireEvent.click(await screen.findByRole("button", { name: "Change Page" }));
    expect(await screen.findByRole("dialog", { name: "Change Page" })).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    // Closing takes the dialog's Back entry off history a task later
    // (useCloseOnBack); let that land so its popstate can't close the dialog
    // P opens next (flaked on slow CI).
    await waitFor(() => expect((window.history.state as Record<string, unknown> | null)?.fbOverlay).toBeUndefined());

    fireEvent.keyDown(window, { key: "c" });
    expect(onCompose).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(window, { key: "p" });
    expect(await screen.findByRole("dialog", { name: "Change Page" })).toBeInTheDocument();
  });

  it("ignores the keys while typing or with a modifier", async () => {
    useSchedule({});
    const onCompose = vi.fn();
    render(
      <>
        <input aria-label="elsewhere" />
        <ActivePageDisplay onCompose={onCompose} />
      </>,
      { wrapper: TestWrapper },
    );
    await screen.findByTestId("now-showing");
    fireEvent.keyDown(screen.getByRole("textbox", { name: "elsewhere" }), { key: "c" });
    fireEvent.keyDown(window, { key: "c", metaKey: true });
    expect(onCompose).not.toHaveBeenCalled();
  });

  it("shows the C / P hints beside the actions", async () => {
    useSchedule({});
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    const hints = await screen.findByTestId("home-key-hints");
    expect(hints).toHaveTextContent("CComposePChange Page");
  });
});

// BB-FH-7, BB-FH-9 (07a `302:20841`): the actions are Button lg (40 px) and
// the card's meta names the hub: "Flagship 22 × 6 · fiestapi.local".
describe("ActivePageDisplay - 07a desktop details", () => {
  it("draws Change Page, Cancel override and Edit page at Button lg", async () => {
    useSchedule({ temporary_override: override(42 * 60) });
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    const card = await screen.findByTestId("now-showing");
    await within(card).findByText("Override");
    for (const name of [/Change Page/, /Cancel override/]) {
      expect(within(card).getByRole("button", { name })).toHaveAttribute("data-size", "lg");
    }
    expect(within(card).getByRole("link", { name: /Edit page/ })).toHaveAttribute("data-size", "lg");
  });

  function atWidth(width: number) {
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query: string) =>
        ({
          matches: (() => {
            const min = /min-width:\s*(\d+)/.exec(query);
            const max = /max-width:\s*(\d+)/.exec(query);
            return (!min || width >= Number(min[1])) && (!max || width <= Number(max[1]));
          })(),
          media: query,
          onchange: null,
          addListener: vi.fn(),
          removeListener: vi.fn(),
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          dispatchEvent: vi.fn(),
        }) as unknown as MediaQueryList,
    );
  }
  function hubNamed(name: string) {
    server.use(http.get(`${API_BASE}/settings/all`, () => HttpResponse.json({ general: { instance_name: name } })));
  }

  it("names the hub after the type and size on a desktop", async () => {
    atWidth(1440);
    hubNamed("Maya’s FiestaPi");
    useSchedule({});
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    const card = await screen.findByTestId("now-showing");
    expect(await within(card).findByText("Flagship 22 × 6 · Maya’s FiestaPi")).toBeInTheDocument();
  });

  it("says the type and size alone when the hub has no name", async () => {
    atWidth(1440);
    hubNamed("");
    useSchedule({});
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    const card = await screen.findByTestId("now-showing");
    expect(await within(card).findByText("Flagship 22 × 6")).toBeInTheDocument();
  });

  it("leaves the hub out at medium width, as the 900 frame does", async () => {
    atWidth(900);
    hubNamed("Maya’s FiestaPi");
    useSchedule({});
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    const card = await screen.findByTestId("now-showing");
    expect(await within(card).findByText("Flagship 22 × 6")).toBeInTheDocument();
    expect(within(card).queryByText(/Maya’s FiestaPi/)).toBeNull();
  });
});
