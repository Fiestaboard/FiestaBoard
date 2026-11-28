import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CreatorIde from "@/components/ide/creator-ide";
import type { PageBuilderDraftState, PageBuilderHandle } from "@/components/page-builder";

import { server } from "./mocks/server";

// The sidebar's global current board. A test may point it at another display
// than the page's own (UX-6-1).
const sidebar = vi.hoisted(() => ({ currentBoardId: "den", loading: false }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/components/current-board-context", () => {
  const boards = [
    { id: "den", name: "Den TV", device_type: "panel", grid_rows: 12, grid_cols: 29 },
    { id: "hall", name: "Hall board", device_type: "flagship" },
    // Another display the page's 29 × 12 grid fits as is (D3: retarget, no copy).
    { id: "office", name: "Office TV", device_type: "panel", grid_rows: 12, grid_cols: 29 },
  ];
  return {
    useCurrentBoard: () => {
      if (sidebar.loading) return { boards: [], currentBoardId: null, currentBoard: undefined, isLoading: true };
      const currentBoard = boards.find((board) => board.id === sidebar.currentBoardId);
      return { boards, currentBoardId: sidebar.currentBoardId, currentBoard, isLoading: false };
    },
  };
});

const PAGE = "commute";
const snapshot = {
  id: PAGE,
  name: "Commute",
  revision: "rev-1",
  device_type: "panel" as const,
  grid_rows: 12,
  grid_cols: 29,
  duration_seconds: 30,
  transition_strategy: "column",
  template: ["NEXT DEPARTURES", '{{muni.next}} {{= DEFAULT(muni.alert, "OK") }}'],
  line_metadata: [],
};

function fakeBuilder(overrides: Partial<{ unsaved: boolean; mirroring: boolean; previewBoardId: string }> = {}) {
  // applyContent behaves like the editor: the restored content is the editor's, unsaved.
  let current: Omit<typeof snapshot, "transition_strategy"> & { transition_strategy: string | null } = snapshot;
  let unsaved = overrides.unsaved ?? false;
  return {
    hasUnsavedChanges: () => unsaved,
    isMirroring: () => overrides.mirroring ?? false,
    // The editor previews this FiestaPanel page as Den TV, the display it fits.
    getPreviewBoardId: () => overrides.previewBoardId ?? "den",
    getCurrentPage: () => current,
    reloadFromServer: vi.fn(() => Promise.resolve()),
    applyContent: vi.fn((content: typeof snapshot) => {
      current = { ...snapshot, ...content };
      unsaved = true;
    }),
    discardContent: vi.fn(() => {
      current = snapshot;
      unsaved = false;
    }),
    requestDelete: vi.fn(),
    // FP-2: Page-tab settings are staged in the editor like any other edit (UX-7-1).
    setPageSettings: vi.fn((settings: { duration_seconds?: number; transition_strategy?: string | null }) => {
      current = { ...current, ...settings };
      unsaved = true;
    }),
    // D3: Shows on retargets the preview to a display of the same size.
    setPreviewBoard: vi.fn(),
  } as unknown as PageBuilderHandle;
}

interface Calls {
  draftPut: unknown[];
  restore: { id: string; body: unknown }[];
  duplicate: unknown[];
  validate: unknown[];
  draftGet: number;
  draftDelete: string[];
}

function mockHub({ draft = null as unknown, restoreConflict = false, live = true, draftConflict = false } = {}) {
  const calls: Calls = { draftPut: [], restore: [], duplicate: [], validate: [], draftGet: 0, draftDelete: [] };
  server.use(
    http.get("/api/v1/pages", () =>
      HttpResponse.json({
        pages: [
          { id: PAGE, name: "Commute", device_type: "panel" },
          { id: "brunch", name: "Weekend brunch", device_type: "panel" },
        ],
        total: 2,
      }),
    ),
    http.get("/api/v1/collections", () =>
      HttpResponse.json({
        collections: [{ id: "col_den", name: "Den rotation", page_ids: ["brunch", PAGE], selection_mode: "time" }],
        total: 1,
      }),
    ),
    http.get("/api/v1/schedules", () =>
      HttpResponse.json({
        schedules: [
          {
            id: "s1",
            page_id: PAGE,
            board_id: "den",
            start_time: "07:30",
            end_time: "08:30",
            day_pattern: "weekdays",
            enabled: true,
            created_at: "",
          },
        ],
        total: 1,
        default_page_id: null,
        enabled: null,
      }),
    ),
    http.get("/api/schedules/active/page", ({ request }) => {
      const board = new URL(request.url).searchParams.get("board_id");
      return HttpResponse.json({
        page_id: board === "den" && live ? PAGE : "other",
        source: "schedule",
        schedule_enabled: true,
        current_time: "07:41",
        current_day: "friday",
        default_page_id: null,
        temporary_override: { active: false },
      });
    }),
    http.post("/api/collections/col_den/dry-run", () =>
      HttpResponse.json({ collection_id: "col_den", page_id: "brunch", timeline: [], shown_on: [], sources: {} }),
    ),
    // GET /pages/drafts: the drafts the hub holds; a saved draft joins the list.
    http.get("/api/pages/drafts", () =>
      HttpResponse.json({
        drafts:
          draft || calls.draftPut.length ? [{ page_id: PAGE, saved_at: "2026-11-17T15:44:00Z", stale: false }] : [],
      }),
    ),
    http.get(`/api/pages/${PAGE}/draft`, () => {
      calls.draftGet += 1;
      return draft ? HttpResponse.json(draft) : HttpResponse.json({ detail: "No draft" }, { status: 404 });
    }),
    http.delete(`/api/pages/${PAGE}/draft`, ({ request }) => {
      calls.draftDelete.push(new URL(request.url).searchParams.get("expected_revision") ?? "none");
      return HttpResponse.json({ page_id: PAGE, discarded: true });
    }),
    http.put(`/api/pages/${PAGE}/draft`, async ({ request }) => {
      const body = (await request.json()) as { expected_revision?: string };
      calls.draftPut.push(body);
      // The hub's guard: another device saved the draft since this editor read it.
      if (draftConflict && body.expected_revision) {
        return HttpResponse.json({ detail: "Draft changed" }, { status: 412 });
      }
      return HttpResponse.json({
        page_id: PAGE,
        revision: "d1",
        saved_at: "2026-11-17T15:44:00Z",
        stale: false,
        content: { ...snapshot, type: "template" },
      });
    }),
    http.get(`/api/pages/${PAGE}/revisions`, () =>
      HttpResponse.json({
        page_id: PAGE,
        total: 2,
        revisions: [
          {
            id: "r2",
            saved_at: "2026-11-17T15:12:00Z",
            origin: "edited",
            via: "phone",
            name: "Commute",
            rows: 12,
            cols: 29,
            current: true,
          },
          {
            id: "r1",
            saved_at: "2026-11-16T21:02:00Z",
            origin: "assistant",
            via: "mcp",
            name: "Commute",
            rows: 12,
            cols: 29,
            current: false,
          },
        ],
      }),
    ),
    http.get(`/api/pages/${PAGE}/revisions/:rev`, ({ params }) =>
      HttpResponse.json({
        id: params.rev,
        saved_at: "2026-11-16T21:02:00Z",
        origin: "edited",
        name: "Commute",
        rows: 12,
        cols: 29,
        current: params.rev === "r2",
        content: {
          ...snapshot,
          type: "template",
          template: params.rev === "r2" ? snapshot.template : ["OLD", snapshot.template[1]],
        },
      }),
    ),
    http.post(`/api/pages/${PAGE}/revisions/:rev/restore`, async ({ params, request }) => {
      const body = (await request.json()) as { replace_draft: boolean };
      calls.restore.push({ id: String(params.rev), body });
      if (restoreConflict && !body.replace_draft) return HttpResponse.json({ detail: "draft exists" }, { status: 409 });
      return HttpResponse.json({
        page_id: PAGE,
        revision: "d2",
        saved_at: "2026-11-17T15:50:00Z",
        stale: false,
        restored_from: params.rev,
        content: { ...snapshot, type: "template" },
      });
    }),
    http.get(`/api/pages/${PAGE}/sends`, () =>
      HttpResponse.json({
        page_id: PAGE,
        total: 2,
        sends: [
          { at: "2026-11-17T15:41:00Z", outcome: "sent", via: "auto", board_id: "den", board_name: "Den TV", count: 1 },
          {
            at: "2026-11-17T14:55:00Z",
            outcome: "failed",
            via: "auto",
            board_id: "den",
            board_name: "Den TV",
            error: "unreachable",
          },
        ],
      }),
    ),
    http.post(`/api/pages/${PAGE}/duplicate`, async ({ request }) => {
      calls.duplicate.push(await request.json());
      return HttpResponse.json(
        {
          page: { id: "copy", name: "Commute (Hall board)" },
          report: {
            rows: 6,
            cols: 22,
            from_rows: 12,
            from_cols: 29,
            lines_too_long: [{ line: 1, max_length: 30 }],
            rows_dropped: [6, 7],
            composite_rows_dropped: [],
            canvases_scaled: 0,
            drawing: null,
          },
        },
        { status: 201 },
      );
    }),
    http.post("/api/templates/validate", async ({ request }) => {
      calls.validate.push(await request.json());
      return HttpResponse.json({
        valid: false,
        rows: 12,
        cols: 29,
        errors: [{ line: 2, column: 0, message: "muni.next doesn't exist", code: "unknown_field" }],
      });
    }),
    http.post("/api/templates/render", () =>
      HttpResponse.json({
        rendered: "NEXT DEPARTURES",
        lines: ["NEXT DEPARTURES"],
        line_count: 1,
        charset: "x",
        charset_issues: [
          {
            row: 0,
            col: 1,
            reason: "char",
            token: { type: "char", value: "é" },
            fallback: { type: "char", value: "E" },
          },
        ],
      }),
    ),
  );
  return calls;
}

function setDesktop(desktop: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: desktop && query.includes("min-width: 1024px"),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

function renderIde(
  builder = fakeBuilder(),
  savedTick = 0,
  onDraftStateChange?: (state: PageBuilderDraftState | undefined) => void,
  onPageDisplaysChange?: (ids: readonly string[]) => void,
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } }),
) {
  const slot = document.createElement("div");
  document.body.append(slot);
  // Every render reports its draft state; the header (page-builder) reads it.
  const draftSpy = vi.fn((state: PageBuilderDraftState | undefined) => onDraftStateChange?.(state));
  const lastDraft = () => draftSpy.mock.lastCall?.[0];
  const builderRef = { current: builder };
  const wrap = (node: ReactNode) => (
    <MemoryRouter>
      <QueryClientProvider client={client}>{node}</QueryClientProvider>
    </MemoryRouter>
  );
  const view = render(
    wrap(
      <CreatorIde
        pageId={PAGE}
        builderRef={builderRef}
        explorerSlot={slot}
        // Commute is a FiestaPanel page: its Explorer opens by default (D2).
        boardKind="panel"
        savedTick={savedTick}
        onDraftStateChange={draftSpy}
        onPageDisplaysChange={onPageDisplaysChange}
      />,
    ),
  );
  const rerenderTick = (tick: number, pageId = PAGE) =>
    view.rerender(
      wrap(
        <CreatorIde
          pageId={pageId}
          builderRef={builderRef}
          explorerSlot={slot}
          boardKind="panel"
          savedTick={tick}
          onDraftStateChange={draftSpy}
          onPageDisplaysChange={onPageDisplaysChange}
        />,
      ),
    );
  return { slot, lastDraft, rerenderTick, client, unmount: view.unmount };
}

beforeEach(() => setDesktop(false));
afterEach(() => {
  sidebar.currentBoardId = "den";
  toast.success.mockClear();
  cleanup();
  document.body.innerHTML = "";
});

describe("Creator IDE below 1024 px", () => {
  it("puts Problems in the Inspector as a sixth tab with its count", async () => {
    mockHub();
    renderIde();
    const tabs = await screen.findAllByRole("tab");
    expect(tabs.map((tab) => tab.textContent)).toEqual(expect.arrayContaining([expect.stringContaining("Problems")]));
    expect(tabs).toHaveLength(6);
    expect(screen.queryByRole("region", { name: "Console" })).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: /Problems/ }));
    expect(await screen.findByText("#REF · Row 2")).toBeInTheDocument();
    expect(screen.getByText("Substitution · Row 1")).toBeInTheDocument();
    expect(screen.getByText("Not shown · the send failed")).toBeInTheDocument();
  });

  it("does not render the Explorer column", async () => {
    mockHub();
    const { slot } = renderIde();
    await screen.findAllByRole("tab");
    expect(slot.childElementCount).toBe(0);
  });
});

describe("Creator IDE at 1024 px and wider", () => {
  beforeEach(() => {
    setDesktop(true);
    // Each test starts from the per-kind default (D2), not a toggle remembered by the last.
    localStorage.removeItem("fiestaboard_ide_explorer:panel");
  });

  it("draws five Inspector tabs and docks Problems | Warnings | Sent in the console", async () => {
    mockHub();
    renderIde();
    const inspector = await screen.findByRole("tablist", { name: "Inspector" });
    expect(
      within(inspector)
        .getAllByRole("tab")
        .map((tab) => tab.textContent),
    ).toEqual(["Data", "Logic", "Page", "Shows on", "History"]);
    const console = screen.getByRole("region", { name: "Console" });
    expect(await within(console).findByRole("tab", { name: "Problems 1" })).toBeInTheDocument();
    expect(await within(console).findByRole("tab", { name: "Warnings 1" })).toBeInTheDocument();
    expect(within(console).getByRole("tab", { name: "Sent" })).toBeInTheDocument();
    expect(await within(console).findByText("#REF · Row 2")).toBeInTheDocument();
    expect(await within(console).findByText(/Sent: .* to Den TV · 1 substitution \(é → E\)/)).toBeInTheDocument();
  });

  it("is a Parts outline on a single-display page: no rows that repeat the header, no apologies (UX-5-2, M2)", async () => {
    mockHub();
    const { slot } = renderIde();
    const nav = await within(slot).findByRole("navigation", { name: "Explorer" });
    // Its parts: the data sources and formulas the template reads, by row.
    const parts = within(nav).getByRole("group", { name: "Parts" });
    expect(within(parts).getByText("muni")).toBeInTheDocument();
    expect(within(parts).getByText("Formulas")).toBeInTheDocument();
    expect(within(parts).getAllByText("Row 2")).toHaveLength(2);
    expect(await within(nav).findByText("Used by Den rotation")).toBeInTheDocument();
    // The page's name and its one display are the header's; Snippets is unsupported here.
    expect(within(nav).queryByRole("group", { name: "This page" })).toBeNull();
    expect(within(nav).queryByRole("group", { name: "Boards" })).toBeNull();
    expect(within(nav).queryByRole("group", { name: "Snippets" })).toBeNull();
    expect(within(nav).queryByText(/aren’t available/)).toBeNull();
    // No other page, no page search, no links away (D2b).
    expect(within(nav).queryByText("Weekend brunch")).toBeNull();
    expect(within(nav).queryByRole("searchbox")).toBeNull();
    expect(within(nav).queryAllByRole("link")).toHaveLength(0);
  });

  it("lists the page and its displays when it shows on more than one, and says nothing of no collection", async () => {
    mockHub();
    server.use(
      http.get("/api/v1/collections", () => HttpResponse.json({ collections: [], total: 0 })),
      http.get("/api/v1/schedules", () =>
        HttpResponse.json({
          schedules: ["den", "hall"].map((board_id) => ({
            id: `s-${board_id}`,
            page_id: PAGE,
            board_id,
            start_time: "07:30",
            end_time: "08:30",
            day_pattern: "weekdays",
            enabled: true,
            created_at: "",
          })),
          total: 2,
          default_page_id: null,
          enabled: null,
        }),
      ),
    );
    const { slot } = renderIde();
    const nav = await within(slot).findByRole("navigation", { name: "Explorer" });
    const boards = await within(nav).findByRole("group", { name: "Boards" });
    expect(within(boards).getByText("Den TV")).toBeInTheDocument();
    expect(within(boards).getByText("Hall board")).toBeInTheDocument();
    expect(within(nav).getByRole("group", { name: "This page" })).toHaveTextContent("Commute");
    expect(within(nav).queryByText("Not in any collection.")).toBeNull();
  });

  it("hides the Explorer to one Show Explorer button and back, moving focus with it (D2)", async () => {
    mockHub();
    const { slot } = renderIde();
    const nav = await within(slot).findByRole("navigation", { name: "Explorer" });
    fireEvent.click(within(nav).getByRole("button", { name: "Hide Explorer" }));
    expect(within(slot).queryByRole("navigation", { name: "Explorer" })).toBeNull();
    const show = within(slot).getByRole("button", { name: "Show Explorer" });
    expect(show).toHaveAttribute("aria-expanded", "false");
    await waitFor(() => expect(show).toHaveFocus());
    expect(localStorage.getItem("fiestaboard_ide_explorer:panel")).toBe("closed");
    fireEvent.click(show);
    const hide = await within(slot).findByRole("button", { name: "Hide Explorer" });
    await waitFor(() => expect(hide).toHaveFocus());
    expect(localStorage.getItem("fiestaboard_ide_explorer:panel")).toBe("open");
  });

  it("keeps the Explorer lists' children listitems (BB-B-20: axe aria-required-children)", async () => {
    mockHub();
    const { slot } = renderIde();
    const nav = await within(slot).findByRole("navigation", { name: "Explorer" });
    // D2b: the Explorer lists the open page's own rows (no page links), still in real lists.
    await within(within(nav).getByRole("group", { name: "Parts" })).findByText("muni");
    const lists = nav.querySelectorAll("ul");
    expect(lists.length).toBeGreaterThan(0);
    for (const list of lists) for (const child of Array.from(list.children)) expect(child.tagName).toBe("LI");
  });

  it("validates at the open display's width with the page geometry", async () => {
    const calls = mockHub();
    renderIde();
    await waitFor(() => expect(calls.validate.length).toBeGreaterThan(0));
    expect(calls.validate[0]).toMatchObject({ board_id: "den", device_type: "panel", grid_rows: 12, grid_cols: 29 });
  });
});

// UX-6-1: the IDE speaks for the page's own display (the one the editor
// previews it as), not the sidebar's global current board.
describe("the page's own display, with another board current in the sidebar", () => {
  beforeEach(() => {
    sidebar.currentBoardId = "hall";
  });

  it("names the page's display on the timeline", async () => {
    setDesktop(true);
    mockHub();
    renderIde();
    expect(await screen.findByText("Timeline · Commute this week · Den TV")).toBeInTheDocument();
    expect(screen.queryByText(/Hall board/)).not.toBeInTheDocument();
  });

  it("says whose default the Transition row overrides", async () => {
    mockHub();
    renderIde();
    expect(await screen.findByRole("button", { name: /Transition/ })).toHaveTextContent("Overrides Den TV’s default");
  });

  it("validates at the page's display, not the sidebar's", async () => {
    const calls = mockHub();
    renderIde();
    await waitFor(() => expect(calls.validate.length).toBeGreaterThan(0));
    expect(calls.validate.every((body) => (body as { board_id?: string }).board_id === "den")).toBe(true);
  });

  it("follows the editor when it previews the page as another display", async () => {
    mockHub();
    const overrides = { previewBoardId: "den" };
    renderIde(fakeBuilder(overrides));
    const transition = await screen.findByRole("button", { name: /Transition/ });
    await waitFor(() => expect(transition).toHaveTextContent("Overrides Den TV’s default"));
    overrides.previewBoardId = "hall";
    await waitFor(() => expect(transition).toHaveTextContent("Overrides Hall board’s default"), { timeout: 3000 });
  });

  it("tells the editor the displays that show the page", async () => {
    mockHub();
    const onPageDisplaysChange = vi.fn();
    renderIde(fakeBuilder(), 0, undefined, onPageDisplaysChange);
    await waitFor(() => expect(onPageDisplaysChange).toHaveBeenLastCalledWith(["den"]));
  });

  // OPUS-2645 S1: a client-side move to another page unmounts the IDE while
  // the next page loads; the editor must not keep previewing this page's displays.
  it("takes its displays back when it closes", async () => {
    mockHub();
    const onPageDisplaysChange = vi.fn();
    const { unmount } = renderIde(fakeBuilder(), 0, undefined, onPageDisplaysChange);
    await waitFor(() => expect(onPageDisplaysChange).toHaveBeenLastCalledWith(["den"]));
    unmount();
    expect(onPageDisplaysChange).toHaveBeenLastCalledWith([]);
  });

  it("names another page's displays, not this one's, when the page changes under it", async () => {
    mockHub();
    // Weekend brunch is showing now on the Hall board.
    server.use(
      http.get("/api/schedules/active/page", ({ request }) =>
        HttpResponse.json({
          page_id: { den: PAGE, hall: "brunch" }[new URL(request.url).searchParams.get("board_id") ?? ""] ?? "other",
          source: "manual",
          schedule_enabled: true,
          current_time: "07:41",
          current_day: "friday",
          default_page_id: null,
          temporary_override: { active: false },
        }),
      ),
    );
    const onPageDisplaysChange = vi.fn();
    const { rerenderTick } = renderIde(fakeBuilder(), 0, undefined, onPageDisplaysChange);
    await waitFor(() => expect(onPageDisplaysChange).toHaveBeenLastCalledWith(["den"]));
    rerenderTick(0, "brunch");
    await waitFor(() => expect(onPageDisplaysChange).toHaveBeenLastCalledWith(["hall"]));
  });

  // OPUS-2645 S2: "showing now" changes with the clock (the IDE re-asks every
  // 60 s); the display the editor previews as must not move while you edit.
  it("holds the displays it first settled on while showing-now changes", async () => {
    mockHub();
    const hub = { denShowsPage: true };
    server.use(
      http.get("/api/v1/schedules", () =>
        HttpResponse.json({
          schedules: [
            {
              id: "s0",
              page_id: PAGE,
              board_id: "hall",
              start_time: "18:00",
              end_time: "19:00",
              day_pattern: "daily",
              enabled: true,
              created_at: "",
            },
            {
              id: "s1",
              page_id: PAGE,
              board_id: "den",
              start_time: "07:30",
              end_time: "08:30",
              day_pattern: "weekdays",
              enabled: true,
              created_at: "",
            },
          ],
          total: 2,
          default_page_id: null,
          enabled: null,
        }),
      ),
      http.get("/api/schedules/active/page", ({ request }) => {
        const board = new URL(request.url).searchParams.get("board_id");
        return HttpResponse.json({
          page_id: board === "den" && hub.denShowsPage ? PAGE : "other",
          source: "schedule",
          schedule_enabled: true,
          current_time: "08:29",
          current_day: "friday",
          default_page_id: null,
          temporary_override: { active: false },
        });
      }),
    );
    const onPageDisplaysChange = vi.fn();
    const { client } = renderIde(fakeBuilder(), 0, undefined, onPageDisplaysChange);
    await waitFor(() => expect(onPageDisplaysChange).toHaveBeenLastCalledWith(["den", "hall"]));
    await screen.findByText(/Showing on Den TV now/);
    // Den's window ends: by the hub's answer the page now shows nowhere, and the
    // schedule lists Hall first.
    hub.denShowsPage = false;
    await act(() => client.refetchQueries({ queryKey: ["ide", "active"] }));
    await waitFor(() => expect(screen.queryByText(/Showing on Den TV now/)).not.toBeInTheDocument());
    expect(onPageDisplaysChange).toHaveBeenLastCalledWith(["den", "hall"]);
    expect(onPageDisplaysChange).not.toHaveBeenCalledWith(["hall", "den"]);
  });

  it("waits for the displays themselves to load", async () => {
    mockHub();
    // On no schedule: only the hub's answer per display says Den TV shows it.
    server.use(
      http.get("/api/v1/schedules", () =>
        HttpResponse.json({ schedules: [], total: 0, default_page_id: null, enabled: null }),
      ),
    );
    sidebar.loading = true;
    const seen: string[] = [];
    const listener = ({ request }: { request: Request }) => {
      seen.push(new URL(request.url).pathname);
    };
    server.events.on("response:mocked", listener);
    const onPageDisplaysChange = vi.fn();
    try {
      const { rerenderTick } = renderIde(fakeBuilder(), 0, undefined, onPageDisplaysChange);
      // Schedules and collections answer while settings are still loading.
      await waitFor(() => expect(seen).toEqual(expect.arrayContaining(["/api/v1/schedules", "/api/v1/collections"])));
      await act(() => new Promise((resolve) => setTimeout(resolve, 50)));
      sidebar.loading = false;
      rerenderTick(0);
      await waitFor(() => expect(onPageDisplaysChange).toHaveBeenLastCalledWith(["den"]));
    } finally {
      sidebar.loading = false;
      server.events.removeListener("response:mocked", listener);
    }
  });

  // OPUS-2647 M1: reopening the editor within the cache's lifetime must pick
  // from the hub's fresh answers, not the cached ones it is re-asking for.
  it("picks from fresh answers, not cached ones, when the editor reopens", async () => {
    mockHub({ live: false });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const first = vi.fn();
    const { unmount } = renderIde(fakeBuilder(), 0, undefined, first, client);
    await waitFor(() => expect(first).toHaveBeenLastCalledWith(["den"]));
    unmount();
    // Meanwhile the page's schedule entry moved to the Hall board.
    server.use(
      http.get("/api/v1/schedules", () =>
        HttpResponse.json({
          schedules: [
            {
              id: "s1",
              page_id: PAGE,
              board_id: "hall",
              start_time: "07:30",
              end_time: "08:30",
              day_pattern: "weekdays",
              enabled: true,
              created_at: "",
            },
          ],
          total: 1,
          default_page_id: null,
          enabled: null,
        }),
      ),
    );
    const reopened = vi.fn();
    renderIde(fakeBuilder(), 0, undefined, reopened, client);
    await waitFor(() => expect(reopened).toHaveBeenLastCalledWith(["hall"]));
    expect(reopened).not.toHaveBeenCalledWith(["den"]);
  });

  it.each([
    ["its schedules", "/api/v1/schedules", "/api/schedules/active/page"],
    ["its collections", "/api/v1/collections", "/api/schedules/active/page"],
    ["the hub's showing-now answers", "/api/schedules/active/page", "/api/v1/schedules"],
  ])("names no display before %s load", async (_what, hanging, served) => {
    mockHub();
    server.use(http.get(hanging, () => new Promise<never>(() => {})));
    const seen: string[] = [];
    const listener = ({ request }: { request: Request }) => {
      seen.push(new URL(request.url).pathname);
    };
    server.events.on("response:mocked", listener);
    const onPageDisplaysChange = vi.fn();
    try {
      renderIde(fakeBuilder(), 0, undefined, onPageDisplaysChange);
      // The other half has answered (either alone would name Den TV)…
      await waitFor(() => expect(seen).toContain(served));
      await act(() => new Promise((resolve) => setTimeout(resolve, 50)));
      // …but the editor is told nothing until both have.
      expect(onPageDisplaysChange).not.toHaveBeenCalledWith(["den"]);
    } finally {
      server.events.removeListener("response:mocked", listener);
    }
  });

  it("says the page's display keeps the live version after a restore", async () => {
    mockHub();
    renderIde();
    fireEvent.click(await screen.findByRole("tab", { name: "History" }));
    fireEvent.click((await screen.findAllByRole("button", { name: /Restore/ }))[0]);
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(toast.success).toHaveBeenLastCalledWith(expect.any(String), {
      description: "Den TV keeps the live version until you publish.",
    });
  });

  it("marks the page's display as this display in Make a copy", async () => {
    mockHub();
    renderIde();
    fireEvent.click(await screen.findByRole("button", { name: /Make a copy for another display/ }));
    expect(await screen.findByRole("button", { name: /Den TV/ })).toHaveTextContent(/This display/i);
    expect(screen.getByRole("button", { name: /Hall board/ })).not.toHaveTextContent(/This display/i);
  });
});

describe("status row and header actions", () => {
  it("says where the page shows now and until when", async () => {
    mockHub();
    renderIde();
    expect(await screen.findByText(/Showing on Den TV now · until 8:30/)).toBeInTheDocument();
  });

  // D6 (UX-1-1): the header meta is the one place for the save state, so the
  // status row carries no Unsaved or Draft chip; Testing (mirroring) stays.
  it("leaves Unsaved and Draft to the header and keeps Testing in the status row", async () => {
    mockHub();
    renderIde(fakeBuilder({ unsaved: true }));
    expect(await screen.findByText(/Showing on Den TV now/)).toBeInTheDocument();
    expect(screen.queryByText("Unsaved")).not.toBeInTheDocument();
    cleanup();
    mockHub();
    renderIde(fakeBuilder({ unsaved: true, mirroring: true }));
    expect(await screen.findByText("Testing")).toBeInTheDocument();
    cleanup();
    mockHub({
      draft: {
        page_id: PAGE,
        revision: "d1",
        saved_at: "2026-11-17T15:44:00Z",
        stale: false,
        content: { ...snapshot, type: "template" },
      },
    });
    const { lastDraft } = renderIde(fakeBuilder({ unsaved: true }));
    await waitFor(() => expect(lastDraft()?.draftSavedAt).toBe("2026-11-17T15:44:00Z"));
    expect(screen.queryByText(/^Draft /)).not.toBeInTheDocument();
    const status = document.querySelector<HTMLElement>('[data-slot="preview-status"]')!;
    expect(status).not.toHaveTextContent(/Draft/);
  });

  it("hands the header Save draft while live, which saves the editor content as the draft", async () => {
    const calls = mockHub();
    const { lastDraft } = renderIde();
    await waitFor(() => expect(lastDraft()?.saveDraft).toBeDefined());
    act(() => lastDraft()!.saveDraft!());
    await waitFor(() => expect(calls.draftPut).toHaveLength(1));
    expect(calls.draftPut[0]).toMatchObject({
      name: "Commute",
      template: snapshot.template,
      grid_rows: 12,
      grid_cols: 29,
    });
  });

  it("keeps the editor's own Save and Show now when no display shows or schedules the page", async () => {
    mockHub({ live: false });
    server.use(
      http.get("/api/v1/schedules", () =>
        HttpResponse.json({ schedules: [], total: 0, default_page_id: null, enabled: null }),
      ),
    );
    const { lastDraft } = renderIde();
    const status = await waitFor(() => {
      const row = document.querySelector<HTMLElement>('[data-slot="preview-status"]');
      expect(row).toHaveAttribute("data-display", "not-scheduled");
      return row!;
    });
    expect(lastDraft()?.saveDraft).toBeUndefined();
    // Said once (BB-E-26): the chip, not the chip and a sentence repeating it.
    expect(within(status).getByText("Not scheduled")).toBeInTheDocument();
    expect(within(status).queryByText("Not on any display’s schedule")).not.toBeInTheDocument();
  });

  it("leaves a saved page's save state to the header, not a second Saved chip (BB-E-26)", async () => {
    mockHub();
    renderIde();
    expect(await screen.findByText(/Showing on Den TV now/)).toBeInTheDocument();
    const status = document.querySelector<HTMLElement>('[data-slot="preview-status"]')!;
    expect(within(status).queryByText("Saved")).not.toBeInTheDocument();
  });

  it("discards a draft this session saved once the editor saves the page itself", async () => {
    const calls = mockHub();
    const { lastDraft, rerenderTick, client } = renderIde();
    await waitFor(() => expect(lastDraft()?.saveDraft).toBeDefined());
    act(() => lastDraft()!.saveDraft!());
    await waitFor(() => expect(calls.draftPut).toHaveLength(1));
    await waitFor(() => expect(client.getQueryData(["ide", "draft", PAGE])).toBeTruthy());
    act(() => rerenderTick(1));
    await waitFor(() => expect(calls.draftDelete).toEqual(["d1"]));
  });

  // E2E page-builder "Saved <time>": once the editor has saved the page, the
  // header must say Saved, not "Draft saved", even before the hub answers the
  // draft discard; the draft this session wrote is behind the page now.
  it("drops the Draft saved label the moment the editor saves the page", async () => {
    const calls = mockHub();
    let unsaved = true;
    const builder = {
      ...fakeBuilder(),
      hasUnsavedChanges: () => unsaved,
    } as unknown as PageBuilderHandle;
    const onDraftStateChange = vi.fn();
    const { rerenderTick } = renderIde(builder, 0, onDraftStateChange);
    // Autosave writes the draft for the dirty editor.
    await waitFor(() => expect(calls.draftPut).toHaveLength(1), { timeout: 5000 });
    await waitFor(() =>
      expect(onDraftStateChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ draftSavedAt: expect.any(String) }),
      ),
    );
    // The editor saves the page: it is clean now, and the shell bumps savedTick.
    unsaved = false;
    act(() => rerenderTick(1));
    await waitFor(() => expect(onDraftStateChange.mock.lastCall![0]?.draftSavedAt).toBeUndefined());
    await waitFor(() => expect(calls.draftDelete).toEqual(["d1"]));
  }, 10_000);

  // BB-B-27: a page without a draft is the usual case, not a failed request:
  // the IDE reads the drafts list first and asks for no draft that isn't there.
  it("asks for no draft the hub doesn't hold, so opening a page logs no 404", async () => {
    const calls = mockHub();
    renderIde();
    await screen.findByText(/Showing on Den TV now/);
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(calls.draftGet).toBe(0);
  });

  // D4 (BB-E-17): a draft the hub holds when the page opens is restored into the
  // editor, so once the editor saves the page that draft is behind it and goes.
  it("restores a hub draft into the editor on open and drops it once the editor saves", async () => {
    const draftContent = { ...snapshot, type: "template", template: ["FROM THE PHONE"] };
    const calls = mockHub({
      draft: {
        page_id: PAGE,
        revision: "phone-1",
        via: "phone",
        saved_at: "2026-11-17T15:44:00Z",
        stale: false,
        content: draftContent,
      },
    });
    const builder = fakeBuilder();
    const onDraftStateChange = vi.fn();
    const { rerenderTick } = renderIde(builder, 0, onDraftStateChange);
    await waitFor(() => expect(builder.applyContent).toHaveBeenCalledWith(draftContent));
    await waitFor(() =>
      expect(onDraftStateChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ label: "Draft restored", onDiscard: expect.any(Function) }),
      ),
    );
    act(() => rerenderTick(1));
    await waitFor(() => expect(calls.draftDelete).toEqual(["phone-1"]));
  });

  it("Discard on a restored draft deletes it and puts the saved page back", async () => {
    const calls = mockHub({
      draft: {
        page_id: PAGE,
        revision: "d7",
        saved_at: "2026-11-17T15:44:00Z",
        stale: true,
        content: { ...snapshot, type: "template", template: ["DRAFT"] },
      },
    });
    const builder = fakeBuilder();
    const onDraftStateChange = vi.fn();
    renderIde(builder, 0, onDraftStateChange);
    await waitFor(() =>
      expect(onDraftStateChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ label: "Draft restored · the page changed since" }),
      ),
    );
    const state = onDraftStateChange.mock.lastCall![0] as { onDiscard: () => void };
    await act(async () => state.onDiscard());
    await waitFor(() => expect(calls.draftDelete).toEqual(["d7"]));
    expect(builder.discardContent).toHaveBeenCalled();
    await waitFor(() => expect(onDraftStateChange.mock.lastCall![0]).not.toHaveProperty("label", "Draft restored"));
  });

  it("autosaves unsaved edits to a saved page as the hub draft, never the page", async () => {
    const calls = mockHub();
    const pagePuts: unknown[] = [];
    server.use(
      http.put(`/api/pages/${PAGE}`, async ({ request }) => {
        pagePuts.push(await request.json());
        return HttpResponse.json({});
      }),
    );
    renderIde(fakeBuilder({ unsaved: true }));
    await waitFor(() => expect(calls.draftPut).toHaveLength(1), { timeout: 5000 });
    expect(calls.draftPut[0]).toMatchObject({ name: "Commute", template: snapshot.template });
    expect(pagePuts).toEqual([]);
  });

  it("does not autosave over a draft this session neither restored nor wrote", async () => {
    // The editor already differs from both: the draft was made elsewhere after
    // these edits began, so it is the reader's to resolve (History), not ours.
    const calls = mockHub({
      draft: {
        page_id: PAGE,
        revision: "other",
        saved_at: "2026-11-17T15:44:00Z",
        stale: false,
        content: { ...snapshot, type: "template", template: ["ELSEWHERE"] },
      },
    });
    renderIde(fakeBuilder({ unsaved: true }));
    await waitFor(() => expect(calls.draftGet).toBeGreaterThan(0));
    await new Promise((resolve) => setTimeout(resolve, 2500));
    expect(calls.draftPut).toEqual([]);
  }, 10_000);

  // FABLE-2583 must-fixes 1-3.
  it("writes no draft when the hub's drafts could not be read", async () => {
    const calls = mockHub();
    server.use(http.get("/api/pages/drafts", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
    renderIde(fakeBuilder({ unsaved: true }));
    await new Promise((resolve) => setTimeout(resolve, 2500));
    expect(calls.draftPut).toEqual([]);
  }, 10_000);

  it("autosaves an edit that changes only the transition, not the text", async () => {
    const calls = mockHub({
      draft: {
        page_id: PAGE,
        revision: "d1",
        saved_at: "2026-11-17T15:44:00Z",
        stale: false,
        content: { ...snapshot, type: "template" },
      },
    });
    // The open restores nothing (the draft matches), then the transition changes.
    const builder = fakeBuilder();
    renderIde(builder);
    await waitFor(() => expect(calls.draftGet).toBeGreaterThan(0));
    act(() => builder.applyContent({ ...snapshot, type: "template", transition_strategy: "wave" }));
    await waitFor(() => expect(calls.draftPut).toHaveLength(1), { timeout: 5000 });
    expect(calls.draftPut[0]).toMatchObject({ transition_strategy: "wave", expected_revision: "d1" });
  }, 10_000);

  it("autosaves an edit that changes only the page duration (UX-7-1)", async () => {
    const calls = mockHub({
      draft: {
        page_id: PAGE,
        revision: "d1",
        saved_at: "2026-11-17T15:44:00Z",
        stale: false,
        content: { ...snapshot, type: "template" },
      },
    });
    const builder = fakeBuilder();
    renderIde(builder);
    await waitFor(() => expect(calls.draftGet).toBeGreaterThan(0));
    act(() => builder.setPageSettings({ duration_seconds: 60 }));
    await waitFor(() => expect(calls.draftPut).toHaveLength(1), { timeout: 5000 });
    expect(calls.draftPut[0]).toMatchObject({ duration_seconds: 60, expected_revision: "d1" });
  }, 10_000);

  it("says autosave is paused, not Draft saved, beside a draft from elsewhere", async () => {
    mockHub({
      draft: {
        page_id: PAGE,
        revision: "other",
        saved_at: "2026-11-17T15:44:00Z",
        stale: false,
        content: { ...snapshot, type: "template", template: ["ELSEWHERE"] },
      },
    });
    const onDraftStateChange = vi.fn();
    renderIde(fakeBuilder({ unsaved: true }), 0, onDraftStateChange);
    await waitFor(() =>
      expect(onDraftStateChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ label: "Unsaved · a draft from elsewhere is waiting in History" }),
      ),
    );
    expect(onDraftStateChange.mock.calls.some(([state]) => state?.draftSavedAt)).toBe(false);
  });

  it("offers Delete page in the Page tab, through the editor's confirmation", async () => {
    mockHub();
    const builder = fakeBuilder();
    renderIde(builder);
    fireEvent.click(await screen.findByRole("button", { name: /^Delete page…/ }));
    expect(builder.requestDelete).toHaveBeenCalledOnce();
  });

  it("guards Save draft with the draft's revision and asks before overwriting a newer one", async () => {
    const calls = mockHub({
      draftConflict: true,
      draft: {
        page_id: PAGE,
        revision: "d0",
        saved_at: "2026-11-17T15:44:00Z",
        stale: false,
        content: { ...snapshot, type: "template" },
      },
    });
    const { lastDraft } = renderIde();
    await waitFor(() => expect(calls.draftGet).toBe(1));
    await waitFor(() => expect(lastDraft()?.saveDraft).toBeDefined());
    act(() => lastDraft()!.saveDraft!());
    const dialog = await screen.findByRole("alertdialog", { name: "Replace the newer draft?" });
    expect(calls.draftPut).toEqual([expect.objectContaining({ expected_revision: "d0" })]);
    fireEvent.click(within(dialog).getByRole("button", { name: "Replace draft" }));
    await waitFor(() => expect(calls.draftPut).toHaveLength(2));
    expect(calls.draftPut[1]).not.toHaveProperty("expected_revision");
  });
});

describe("Inspector tabs", () => {
  it("lists the page's data and formulas", async () => {
    mockHub();
    renderIde();
    fireEvent.click(await screen.findByRole("tab", { name: "Data" }));
    expect(await screen.findByText("muni.next")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Logic" }));
    expect(await screen.findByText('DEFAULT(muni.alert, "OK")')).toBeInTheDocument();
  });

  it("shows the Page tab rows as drawn", async () => {
    mockHub();
    renderIde();
    expect(await screen.findByRole("button", { name: /Page duration/ })).toHaveTextContent("30 s");
    expect(screen.getByRole("button", { name: /Transition/ })).toHaveTextContent("Overrides Den TV’s default");
    expect(screen.getByRole("button", { name: /When data is missing/ })).toHaveTextContent("1 formula uses DEFAULT");
  });

  // D6 moved the desktop page-transition picker out of the header; the
  // Inspector's Transition row must still offer transition plugins (beta) and
  // name a page's plugin override, or that override can't be set on desktop.
  it("offers transition plugins in the Page tab's Transition menu while the beta is on", async () => {
    mockHub();
    server.use(
      http.get("/api/settings/plugins", () => HttpResponse.json({ transition_plugins_enabled: true })),
      http.get("/api/plugins", () =>
        HttpResponse.json({
          plugins: [{ id: "typewriter", name: "Typewriter", plugin_type: "transition", enabled: true }],
          total: 1,
        }),
      ),
    );
    const builder = fakeBuilder();
    renderIde(builder);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Transition/ }));
    await user.click(await screen.findByRole("menuitemradio", { name: "Typewriter" }));
    // Staged in the editor like any edit; Save writes it (UX-7-1).
    expect(builder.setPageSettings).toHaveBeenCalledWith({ transition_strategy: "plugin:typewriter" });
  });

  it("names a page's transition-plugin override on the Transition row", async () => {
    mockHub();
    server.use(
      http.get("/api/settings/plugins", () => HttpResponse.json({ transition_plugins_enabled: true })),
      http.get("/api/plugins", () =>
        HttpResponse.json({
          plugins: [{ id: "typewriter", name: "Typewriter", plugin_type: "transition", enabled: true }],
          total: 1,
        }),
      ),
    );
    const builder = fakeBuilder();
    const original = builder.getCurrentPage;
    builder.getCurrentPage = () => ({ ...original()!, transition_strategy: "plugin:typewriter" });
    renderIde(builder);
    await waitFor(() => expect(screen.getByRole("button", { name: /Transition/ })).toHaveTextContent("Typewriter"));
  });

  it("answers Shows on with the hub's Now and the collection's rule dry run", async () => {
    mockHub();
    renderIde();
    fireEvent.click(await screen.findByRole("tab", { name: "Shows on" }));
    const now = await screen.findByRole("button", { name: /Weekdays/ });
    await waitFor(() => expect(now).toHaveTextContent("Now"));
    expect(await screen.findByText(/Collection · 2 of 2 · showing Weekend brunch now/)).toBeInTheDocument();
  });

  it("makes a copy for another display and shows the crop report", async () => {
    const calls = mockHub();
    renderIde();
    fireEvent.click(await screen.findByRole("button", { name: /Make a copy for another display/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Hall board/ }));
    expect(await screen.findByText("22 × 6 (was 29 × 12)")).toBeInTheDocument();
    expect(calls.duplicate).toEqual([{ board_id: "hall" }]);
    expect(screen.getByText("2 rows didn’t fit")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the copy" })).toHaveAttribute("href", "/pages/edit/copy");
    // BB-B-23: one way to close (the X), not a Close button beside it too.
    expect(screen.getAllByRole("button", { name: "Close" })).toHaveLength(1);
  });

  // BB-B-23: on a phone the copy result is a sheet like the rest of the phone
  // UI, its title clear of the close button.
  it("shows the copy on a phone as a bottom sheet", async () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes("max-width: 639px") || query.includes("max-width: 1023"),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
    })) as unknown as typeof window.matchMedia;
    mockHub();
    renderIde();
    fireEvent.click(await screen.findByRole("button", { name: /Make a copy for another display/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Hall board/ }));
    await screen.findByText("22 × 6 (was 29 × 12)");
    const sheet = screen.getByRole("dialog");
    expect(sheet).toHaveAttribute("data-slot", "sheet-content");
    expect(sheet).toHaveAttribute("data-side", "bottom");
    expect(sheet.querySelector('[data-slot="sheet-header"]')).toHaveClass("pr-12");
  });
});

describe("History", () => {
  it("restores into a draft and asks before replacing an existing one, never retrying on its own", async () => {
    const calls = mockHub({ restoreConflict: true });
    renderIde();
    fireEvent.click(await screen.findByRole("tab", { name: "History" }));
    const restore = await screen.findAllByRole("button", { name: /Restore/ });
    fireEvent.click(restore[0]);
    const dialog = await screen.findByRole("alertdialog", { name: "Replace the draft?" });
    expect(calls.restore).toEqual([{ id: "r1", body: { replace_draft: false } }]);
    fireEvent.click(within(dialog).getByRole("button", { name: "Replace draft" }));
    await waitFor(() => expect(calls.restore).toHaveLength(2));
    expect(calls.restore[1]).toEqual({ id: "r1", body: { replace_draft: true } });
  });

  it("compares a version against the live page", async () => {
    mockHub();
    renderIde();
    fireEvent.click(await screen.findByRole("tab", { name: "History" }));
    const compare = await screen.findAllByRole("button", { name: /Compare/ });
    fireEvent.click(compare[1]);
    const diff = await screen.findByRole("group", { name: "Version comparison" });
    expect(await within(diff).findByText("Row 1: “OLD” → “NEXT DEPARTURES”")).toBeInTheDocument();
    // The kit appends the version's time to the Restore label itself: it must appear once.
    const restore = within(diff).getByRole("button", { name: /^Restore/ });
    expect(restore.textContent?.match(/\d:\d\d/g)).toHaveLength(1);
  });
});

// FP-2 (UX-AUDIT-1 + FABLE-AUDIT-REVIEW-1): a truthful, quiet IDE.
describe("truthful, quiet IDE (FP-2)", () => {
  beforeEach(() => {
    // Friday 27 Nov 2026, 10:00 local: the next weekday window is Monday's.
    vi.useFakeTimers({ toFake: ["Date"], shouldAdvanceTime: true });
    vi.setSystemTime(new Date(2026, 10, 27, 10, 0));
    localStorage.removeItem("fiestaboard_ide_explorer:panel");
  });
  afterEach(() => vi.useRealTimers());

  const quietHub = () =>
    server.use(
      http.post("/api/templates/validate", () => HttpResponse.json({ valid: true, rows: 12, cols: 29, errors: [] })),
      http.post("/api/templates/render", () =>
        HttpResponse.json({ rendered: "", lines: [], line_count: 0, charset: "x", charset_issues: [] }),
      ),
    );
  const noSchedules = () =>
    server.use(
      http.get("/api/v1/schedules", () =>
        HttpResponse.json({ schedules: [], total: 0, default_page_id: null, enabled: null }),
      ),
    );

  it("says when and where a scheduled page shows next, in words the pill doesn't repeat (UX-6-2)", async () => {
    mockHub({ live: false });
    renderIde();
    const status = await waitFor(() => {
      const row = document.querySelector<HTMLElement>('[data-slot="preview-status"]');
      expect(row).toHaveAttribute("data-display", "scheduled");
      return row!;
    });
    await waitFor(() =>
      expect(within(status).getByText(/^Weekdays 7:30.*8:30.* on Den TV · next Mon 7:30/)).toBeInTheDocument(),
    );
    expect(status).not.toHaveTextContent(/Scheduled on/);
    expect(await within(status).findByRole("button", { name: "1 problem" })).toBeInTheDocument();
  });

  it("shows a zero-problem console as one line that opens on click (M1)", async () => {
    setDesktop(true);
    mockHub();
    quietHub();
    renderIde();
    const consoleRegion = await screen.findByRole("region", { name: "Console" });
    const line = await within(consoleRegion).findByRole("button", { name: /^No problems · Sent .* to Den TV$/ });
    expect(line).toHaveAttribute("aria-expanded", "false");
    expect(within(consoleRegion).queryByRole("tab")).toBeNull();
    fireEvent.click(line);
    expect(await within(consoleRegion).findByRole("tab", { name: "Problems 0" })).toBeInTheDocument();
  });

  it("keeps the console open while there are problems", async () => {
    setDesktop(true);
    mockHub();
    renderIde();
    const consoleRegion = await screen.findByRole("region", { name: "Console" });
    expect(await within(consoleRegion).findByRole("tab", { name: "Problems 1" })).toBeInTheDocument();
    expect(within(consoleRegion).queryByRole("button", { name: /^No problems/ })).toBeNull();
  });

  it("draws the week as one line, not a calendar (UX-6-3 app side)", async () => {
    setDesktop(true);
    mockHub({ live: false });
    renderIde();
    const timeline = await waitFor(() => {
      const card = document.querySelector<HTMLElement>('[data-slot="ide-timeline"]');
      expect(card).not.toBeNull();
      return card!;
    });
    await waitFor(() => expect(timeline).toHaveTextContent(/Weekdays 7:30.*8:30.* · next Mon$/));
    expect(timeline.querySelector('[data-slot="ide-week"]')).toBeNull();
  });

  it("offers Add to schedule on the one-line week of an unscheduled page", async () => {
    setDesktop(true);
    mockHub({ live: false });
    noSchedules();
    renderIde();
    const timeline = await waitFor(() => {
      const card = document.querySelector<HTMLElement>('[data-slot="ide-timeline"]');
      expect(card).toHaveTextContent("Not scheduled this week");
      return card!;
    });
    expect(within(timeline).getByRole("link", { name: "Add to schedule" })).toHaveAttribute(
      "href",
      `/schedule?prefill_page_id=${PAGE}`,
    );
  });

  it("stages Page duration from an inline menu on its row: no modal, no save (UX-7-1)", async () => {
    const calls = mockHub();
    const puts: unknown[] = [];
    server.use(
      http.put(`/api/v1/pages/${PAGE}`, async ({ request }) => {
        puts.push(await request.json());
        return HttpResponse.json({ page: snapshot, incompatible_references: [] });
      }),
    );
    const builder = fakeBuilder();
    renderIde(builder);
    const user = userEvent.setup();
    const row = await screen.findByRole("button", { name: /Page duration/ });
    expect(row).not.toHaveTextContent(/right away/);
    await user.click(row);
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.click(await screen.findByRole("menuitemradio", { name: "1 min" }));
    expect(builder.setPageSettings).toHaveBeenCalledWith({ duration_seconds: 60 });
    expect(puts).toEqual([]);
    expect(calls.draftPut).toEqual([]);
  });

  it("says what to do on a disabled When data is missing row (UX-7-2)", async () => {
    mockHub();
    const builder = fakeBuilder();
    const original = builder.getCurrentPage;
    builder.getCurrentPage = () => ({ ...original()!, template: ["NEXT DEPARTURES", "{{muni.next}}"] });
    renderIde(builder);
    const row = await screen.findByRole("button", { name: /When data is missing/ });
    await waitFor(() => expect(row).toHaveTextContent("Add a fallback to a formula to set this"));
    expect(row).toBeDisabled();
  });

  it("puts the display picker in Shows on: same size retargets, another size offers a copy sized for it (D3)", async () => {
    const calls = mockHub();
    const builder = fakeBuilder();
    renderIde(builder);
    fireEvent.click(await screen.findByRole("tab", { name: "Shows on" }));
    const group = await screen.findByRole("group", { name: "Display" });
    // The page's own display is a fact, not a control (Fable FABLE-2650).
    expect(within(group).queryByRole("button", { name: /Den TV/ })).toBeNull();
    expect(within(group).getByText("Den TV").closest('[aria-current="true"]')).toHaveTextContent("This display");
    fireEvent.click(within(group).getByRole("button", { name: /Office TV/ }));
    expect(builder.setPreviewBoard).toHaveBeenCalledWith("office");
    const hall = within(group).getByRole("button", { name: /Hall board/ });
    expect(hall).toHaveTextContent("Make a copy sized for Hall board");
    fireEvent.click(hall);
    const dialog = await screen.findByRole("dialog", { name: "Make a copy sized for Hall board" });
    // Before the copy it says what the copy will be; the report caption waits for the report (FABLE-2650).
    expect(dialog).toHaveTextContent("Makes a new page sized for Hall board (22 × 6); this page is unchanged.");
    expect(dialog).not.toHaveTextContent("What changed for the new size:");
    fireEvent.click(within(dialog).getByRole("button", { name: "Make the copy" }));
    await waitFor(() => expect(calls.duplicate).toEqual([{ board_id: "hall" }]));
    expect(await screen.findByText("22 × 6 (was 29 × 12)")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toHaveTextContent("What changed for the new size:");
  });

  it("groups Shows on as Display, Schedule and Collections, with copies only per display", async () => {
    mockHub();
    renderIde();
    fireEvent.click(await screen.findByRole("tab", { name: "Shows on" }));
    expect(await screen.findByRole("group", { name: "Schedule" })).toHaveTextContent(/Weekdays/);
    expect(await screen.findByRole("group", { name: "Collections" })).toHaveTextContent("Den rotation");
    const panel = document.querySelector<HTMLElement>('[data-slot="ide-shows-on"]')!;
    expect(within(panel).queryByRole("button", { name: "Make a copy…" })).toBeNull();
  });

  it("moves focus into the console from the problems link, and folds an opened quiet console back", async () => {
    setDesktop(true);
    mockHub();
    quietHub();
    renderIde();
    const status = await waitFor(() => document.querySelector<HTMLElement>('[data-slot="preview-status"]')!);
    fireEvent.click(await within(status).findByRole("button", { name: "0 problems" }));
    const consoleRegion = screen.getByRole("region", { name: "Console" });
    await waitFor(() => expect(within(consoleRegion).getByRole("tab", { name: "Problems 0" })).toHaveFocus());
    fireEvent.click(within(consoleRegion).getByRole("button", { name: "Collapse the console" }));
    const line = await within(consoleRegion).findByRole("button", { name: /^No problems/ });
    await waitFor(() => expect(line).toHaveFocus());
    expect(within(consoleRegion).queryByRole("tab")).toBeNull();
  });
});
