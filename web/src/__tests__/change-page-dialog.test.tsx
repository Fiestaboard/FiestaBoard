import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { toast } from "sonner";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChangePageDialog, type ChangePageDialogProps } from "@/components/home/change-page-dialog";
import type { BoardInstance, SetTemporaryOverrideRequest } from "@/lib/api";

import { server } from "./mocks/server";

const API = "/api";
const NOW = new Date(2026, 10, 13, 18, 16, 0);
const NINE_PM = new Date(2026, 10, 13, 21, 0, 0);

const kitchen = {
  id: "kitchen",
  name: "Kitchen board",
  device_type: "flagship",
  board_color: "black",
} as BoardInstance;

function pagesResponse() {
  const base = { type: "template", device_type: "flagship", duration_seconds: 300, created_at: "2026-01-01T00:00:00Z" };
  return {
    pages: [
      { ...base, id: "taco", name: "Taco Tuesday" },
      { ...base, id: "good-night", name: "Good night" },
      { ...base, id: "commute", name: "Evening commute" },
      { ...base, id: "note-only", name: "Fridge list", device_type: "note" },
    ],
    total: 4,
  };
}

function setup(props: Partial<ChangePageDialogProps> = {}) {
  server.use(
    http.get(`${API}/v1/pages`, () => HttpResponse.json(pagesResponse())),
    http.get(`${API}/v1/collections`, () =>
      HttpResponse.json({
        collections: [{ id: "collection:weekday", name: "Weekday mornings", page_ids: ["taco", "commute"] }],
        total: 1,
      }),
    ),
  );
  const onOpenChange = vi.fn();
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <ChangePageDialog
        open
        onOpenChange={onOpenChange}
        board={kitchen}
        isPrimary
        scheduleEnabled
        currentPageId="commute"
        nextChange={{ at: NINE_PM, pageId: "good-night" }}
        now={() => NOW}
        {...props}
      />
    </QueryClientProvider>,
  );
  return { onOpenChange };
}

function captureOverride() {
  const seen: SetTemporaryOverrideRequest[] = [];
  server.use(
    http.post(`${API}/settings/temporary-override`, async ({ request }) => {
      seen.push((await request.json()) as SetTemporaryOverrideRequest);
      return HttpResponse.json({ active: true });
    }),
  );
  return seen;
}

afterEach(() => {
  server.resetHandlers();
  vi.restoreAllMocks();
});

describe("ChangePageDialog (desktop)", () => {
  it("lists the pages that fit the display, marking the one showing now", async () => {
    setup();
    const dialog = await screen.findByRole("dialog", { name: "Change Page" });
    expect(
      within(dialog).getByText("Pick what Kitchen board shows. Nothing changes until you choose Show now."),
    ).toBeInTheDocument();
    await within(dialog).findByRole("button", { name: /Taco Tuesday/ });
    expect(within(dialog).getByRole("button", { name: /Evening commute.*Showing now/ })).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: /Fridge list/ })).not.toBeInTheDocument();
  });

  it("filters by the search box and switches to Collections", async () => {
    setup();
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByRole("button", { name: /Taco Tuesday/ });
    fireEvent.change(within(dialog).getByRole("searchbox", { name: "Search pages and collections" }), {
      target: { value: "good" },
    });
    expect(within(dialog).getByRole("button", { name: /Good night/ })).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: /Taco Tuesday/ })).not.toBeInTheDocument();
    fireEvent.change(within(dialog).getByRole("searchbox"), { target: { value: "" } });
    fireEvent.click(within(dialog).getByRole("radio", { name: "Collections" }));
    expect(await within(dialog).findByRole("button", { name: /Weekday mornings.*2 pages/ })).toBeInTheDocument();
  });

  it("keeps Show now disabled until a page is picked, then previews it unsent", async () => {
    setup();
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "Show now" })).toBeDisabled();
    fireEvent.click(await within(dialog).findByRole("button", { name: /Taco Tuesday/ }));
    expect(within(dialog).getByText("Not sent yet · Taco Tuesday on Kitchen board")).toBeInTheDocument();
    expect(
      within(dialog).getByRole("radiogroup", { name: "How long should Taco Tuesday stay up?" }),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole("radio", { name: "Until 9:00 PM" })).toHaveAttribute("aria-checked", "true");
    expect(within(dialog).getByRole("button", { name: "Show now" })).toBeEnabled();
  });

  it("holds the page Until the next change on this display (H1 board_id, H2 minutes)", async () => {
    const seen = captureOverride();
    const { onOpenChange } = setup();
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByRole("button", { name: /Taco Tuesday/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Show now" }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0]).toEqual({ board_id: "kitchen", page_id: "taco", duration_minutes: 164, revert_mode: "schedule" });
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it("sends no duration for Until I cancel in Schedule Mode", async () => {
    const seen = captureOverride();
    setup();
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByRole("button", { name: /Taco Tuesday/ }));
    fireEvent.click(within(dialog).getByRole("radio", { name: "Until I cancel" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Show now" }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0]).toEqual({ board_id: "kitchen", page_id: "taco", revert_mode: "schedule" });
  });

  it("pins the page in Manual Mode for Until I cancel, with no Override", async () => {
    const overrides = captureOverride();
    const pins: unknown[] = [];
    server.use(
      http.put(`${API}/settings/active-page`, async ({ request }) => {
        pins.push(await request.json());
        return HttpResponse.json({ page_id: "taco", sent_to_board: true, paused: false, error: null, warnings: [] });
      }),
    );
    setup({ scheduleEnabled: false, nextChange: null, manualPageName: "Evening commute" });
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByRole("button", { name: /Taco Tuesday/ }));
    expect(within(dialog).getByRole("radio", { name: "Until I cancel" })).toHaveAttribute("aria-checked", "true");
    expect(within(dialog).getByText("Stays until you change it. Schedule Mode stays off.")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Show now" }));
    await waitFor(() => expect(pins).toHaveLength(1));
    expect(pins[0]).toEqual({ page_id: "taco", board_id: "kitchen", override_silence: true });
    expect(overrides).toHaveLength(0);
  });

  it("holds a timed Override in Manual Mode", async () => {
    const seen = captureOverride();
    setup({ scheduleEnabled: false, nextChange: null, manualPageName: "Evening commute" });
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByRole("button", { name: /Taco Tuesday/ }));
    fireEvent.click(within(dialog).getByRole("radio", { name: "15 min" }));
    expect(within(dialog).getByText("Holds until 6:31 PM (15m), then Evening commute comes back.")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Show now" }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0]).toEqual({ board_id: "kitchen", page_id: "taco", duration_minutes: 15, revert_mode: "schedule" });
  });

  it("targets the primary display without a board_id", async () => {
    const seen = captureOverride();
    setup({ board: undefined, boardName: "Flagship" });
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByRole("button", { name: /Taco Tuesday/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Show now" }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0]).not.toHaveProperty("board_id");
  });

  it("says a new hold replaces the running Override", async () => {
    setup({ overrideName: "Focus time", nextChange: null });
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByRole("button", { name: /Taco Tuesday/ }));
    expect(within(dialog).getByText(/Replaces the Focus time Override\./)).toBeInTheDocument();
  });

  it("warns that Show now wakes a silenced display", async () => {
    setup({ silence: { until: "7:00 AM" } });
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Show now wakes Kitchen board from its Silence Schedule.")).toBeInTheDocument();
  });

  it("starts on the page it was opened for", async () => {
    setup({ initialPageId: "good-night" });
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Not sent yet · Good night on Kitchen board")).toBeInTheDocument();
  });
});

describe("ChangePageDialog (phone, two steps)", () => {
  function asPhone() {
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query: string) =>
        ({
          matches: query.includes("max-width"),
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

  it("pushes the duration step when a row is tapped, and Back returns to the list", async () => {
    asPhone();
    setup();
    const sheet = await screen.findByRole("dialog", { name: "Change Page" });
    expect(within(sheet).getByText("Step 1 of 2 · Pick what Kitchen board shows.")).toBeInTheDocument();
    expect(within(sheet).queryByRole("button", { name: "Show now" })).not.toBeInTheDocument();
    fireEvent.click(await within(sheet).findByRole("button", { name: /Taco Tuesday/ }));
    const step2 = await screen.findByRole("dialog", { name: "Taco Tuesday" });
    expect(
      within(step2).getByText("Step 2 of 2 · Shows on Kitchen board when you choose Show now."),
    ).toBeInTheDocument();
    expect(within(step2).getByRole("button", { name: "Show now" })).toBeEnabled();
    fireEvent.click(within(step2).getByRole("button", { name: "Back" }));
    expect(await screen.findByRole("dialog", { name: "Change Page" })).toBeInTheDocument();
  });
});

describe("ChangePageDialog review fixes (M1, M2, S1)", () => {
  function trackHub() {
    const calls: string[] = [];
    server.use(
      http.delete(`${API}/settings/temporary-override`, ({ request }) => {
        calls.push(`DELETE override ${new URL(request.url).searchParams.get("board_id")}`);
        return HttpResponse.json({ revert_mode: "schedule" });
      }),
      http.put(`${API}/settings/active-page`, async ({ request }) => {
        const body = (await request.json()) as { page_id: string; board_id?: string };
        calls.push(`PUT pin ${body.page_id} ${body.board_id}`);
        return HttpResponse.json({
          page_id: body.page_id,
          sent_to_board: true,
          paused: false,
          error: null,
          warnings: [],
        });
      }),
      http.post(`${API}/settings/temporary-override`, async ({ request }) => {
        const body = (await request.json()) as SetTemporaryOverrideRequest;
        calls.push(`POST override ${body.board_id} ${body.duration_minutes ?? "none"}`);
        return HttpResponse.json({ active: true });
      }),
      http.post(`${API}/v1/boards/:board/restore`, ({ params }) => {
        calls.push(`restore ${String(params.board)}`);
        return HttpResponse.json({
          board_id: params.board,
          page_id: null,
          sent: true,
          reason: null,
          device_observed: false,
        });
      }),
      http.post(`${API}/force-refresh`, () => {
        calls.push("force-refresh");
        return HttpResponse.json({ message: "ok", sent: true });
      }),
    );
    return calls;
  }

  it("in Manual Mode during an Override, Until I cancel clears that display's override first, then pins", async () => {
    const calls = trackHub();
    setup({ scheduleEnabled: false, nextChange: null, manualPageName: "Evening commute", overrideName: "Dinner note" });
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByRole("button", { name: /Taco Tuesday/ }));
    expect(
      within(dialog).getByText(
        "Stays until you change it. Schedule Mode stays off. Replaces the Dinner note Override.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Show now" }));
    await waitFor(() => expect(calls).toContain("PUT pin taco kitchen"));
    expect(calls).toEqual(["DELETE override kitchen", "PUT pin taco kitchen"]);
  });

  it("a pin is followed by no extra repaint of any display (m16)", async () => {
    const dismiss = vi.spyOn(toast, "dismiss");
    const calls = trackHub();
    const { onOpenChange } = setup({ scheduleEnabled: false, nextChange: null });
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByRole("button", { name: /Taco Tuesday/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Show now" }));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    await new Promise((r) => setTimeout(r, 50));
    expect(calls).toEqual(["PUT pin taco kitchen"]);
    expect(dismiss).toHaveBeenCalledWith("home-override-undo:kitchen");
  });

  it("an override nudges only its own display, not the whole install (S1)", async () => {
    const calls = trackHub();
    setup();
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByRole("button", { name: /Taco Tuesday/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Show now" }));
    await waitFor(() => expect(calls).toContain("restore kitchen"));
    expect(calls).not.toContain("force-refresh");
  });

  it("never sends an indefinite hold when the chosen next-change chip goes away (M2)", async () => {
    const calls = trackHub();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    server.use(http.get(`${API}/v1/pages`, () => HttpResponse.json(pagesResponse())));
    const props = {
      open: true,
      onOpenChange: vi.fn(),
      board: kitchen,
      isPrimary: true,
      scheduleEnabled: true,
      now: () => NOW,
    };
    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <ChangePageDialog {...props} nextChange={{ at: NINE_PM, pageId: null }} />
      </QueryClientProvider>,
    );
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByRole("button", { name: /Taco Tuesday/ }));
    // An explicit tap on the chip, not just the preselection.
    fireEvent.click(within(dialog).getByRole("radio", { name: "1 hr" }));
    fireEvent.click(within(dialog).getByRole("radio", { name: "Until 9:00 PM" }));
    expect(within(dialog).getByRole("radio", { name: "Until 9:00 PM" })).toHaveAttribute("aria-checked", "true");
    rerender(
      <QueryClientProvider client={queryClient}>
        <ChangePageDialog {...props} nextChange={null} />
      </QueryClientProvider>,
    );
    // The chip is gone; Schedule Mode's explicit default (1 hr) is selected instead.
    expect(within(dialog).getByRole("radio", { name: "1 hr" })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(within(dialog).getByRole("button", { name: "Show now" }));
    await waitFor(() => expect(calls).toContain("POST override kitchen 60"));
  });

  it("lists each page's display type and whether the Schedule uses it (07a row meta)", async () => {
    server.use(
      http.get(`${API}/v1/schedules`, () =>
        HttpResponse.json({
          schedules: [{ id: "s1", page_id: "good-night", start_time: "21:00", day_pattern: "all", enabled: true }],
          total: 1,
          default_page_id: null,
          enabled: true,
        }),
      ),
    );
    setup();
    const dialog = await screen.findByRole("dialog");
    expect(
      await within(dialog).findByRole("button", { name: /Good night.*Flagship · Schedule, 9:00 PM/ }),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: /Taco Tuesday.*Flagship · not in the Schedule/ }),
    ).toBeInTheDocument();
  });

  it("offers only collections with a page that fits the display (S5)", async () => {
    setup();
    // After setup: the latest handler wins, and the list is read on demand.
    server.use(
      http.get(`${API}/v1/collections`, () =>
        HttpResponse.json({
          collections: [
            { id: "collection:fits", name: "Fits", page_ids: ["taco"] },
            { id: "collection:notes", name: "Notes only", page_ids: ["note-only"] },
          ],
          total: 2,
        }),
      ),
    );
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByRole("button", { name: /Taco Tuesday/ });
    fireEvent.click(within(dialog).getByRole("radio", { name: "Collections" }));
    expect(await within(dialog).findByRole("button", { name: /^Fits/ })).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: /Notes only/ })).not.toBeInTheDocument();
  });
});
