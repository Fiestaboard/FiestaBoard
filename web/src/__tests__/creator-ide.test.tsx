import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CreatorIde from "@/components/ide/creator-ide";
import type { PageBuilderHandle, PageBuilderSaveActions } from "@/components/page-builder";

import { server } from "./mocks/server";

vi.mock("@/components/current-board-context", () => {
  const boards = [
    { id: "den", name: "Den TV", device_type: "panel" },
    { id: "hall", name: "Hall board", device_type: "flagship" },
  ];
  return {
    useCurrentBoard: () => ({ boards, currentBoardId: "den", currentBoard: boards[0], isLoading: false }),
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

function fakeBuilder(overrides: Partial<{ unsaved: boolean; mirroring: boolean }> = {}) {
  return {
    hasUnsavedChanges: () => overrides.unsaved ?? false,
    isMirroring: () => overrides.mirroring ?? false,
    getCurrentPage: () => snapshot,
    reloadFromServer: vi.fn(() => Promise.resolve()),
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

function renderIde(builder = fakeBuilder(), savedTick = 0) {
  const slot = document.createElement("div");
  document.body.append(slot);
  const onSaveActionsChange = vi.fn();
  const builderRef = { current: builder };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
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
        onSaveActionsChange={onSaveActionsChange}
      />,
    ),
  );
  const rerenderTick = (tick: number) =>
    view.rerender(
      wrap(
        <CreatorIde
          pageId={PAGE}
          builderRef={builderRef}
          explorerSlot={slot}
          boardKind="panel"
          savedTick={tick}
          onSaveActionsChange={onSaveActionsChange}
        />,
      ),
    );
  return { slot, onSaveActionsChange, rerenderTick, client };
}

const latestRenderer = (spy: ReturnType<typeof vi.fn>) => {
  const call = [...spy.mock.calls].reverse().find(([value]) => typeof value === "function");
  return call ? (call[0] as () => (actions: PageBuilderSaveActions) => ReactNode)() : undefined;
};

beforeEach(() => setDesktop(false));
afterEach(() => {
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
    // The week legend names each entry; the narrow blocks only carry their start time.
    const legend = await screen.findByRole("list", { name: "Schedule entries" });
    expect(legend).toHaveTextContent(/Weekdays 7:30.*8:30.* · Den TV/);
  });

  it("scopes the Explorer to the open page: its boards, parts and snippets, no other pages (D2b)", async () => {
    mockHub();
    const { slot } = renderIde();
    const nav = await within(slot).findByRole("navigation", { name: "Explorer" });
    // This page, and only this page: no list of the hub's pages, no page search, no links away.
    const thisPage = within(nav).getByRole("group", { name: "This page" });
    expect(thisPage).toHaveTextContent("Commute");
    expect(within(nav).queryByText("Weekend brunch")).toBeNull();
    expect(within(nav).queryByRole("searchbox")).toBeNull();
    expect(within(nav).queryAllByRole("link")).toHaveLength(0);
    // Its boards: the display it is live or scheduled on.
    expect(await within(within(nav).getByRole("group", { name: "Boards" })).findByText("Den TV")).toBeInTheDocument();
    // Its parts: the data sources and formulas the template reads, by row.
    const parts = within(nav).getByRole("group", { name: "Parts" });
    expect(within(parts).getByText("muni")).toBeInTheDocument();
    expect(within(parts).getByText("Formulas")).toBeInTheDocument();
    expect(within(parts).getAllByText("Row 2")).toHaveLength(2);
    expect(within(nav).getByRole("group", { name: "Snippets" })).toBeInTheDocument();
    expect(await within(nav).findByText("Used by Den rotation")).toBeInTheDocument();
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
    await within(within(nav).getByRole("group", { name: "This page" })).findByText("Commute");
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

describe("status row and header actions", () => {
  it("says where the page shows now and until when", async () => {
    mockHub();
    renderIde();
    expect(await screen.findByText(/Showing on Den TV now · until 8:30/)).toBeInTheDocument();
  });

  it("derives Unsaved, Testing and Draft from the editor and the hub draft", async () => {
    mockHub();
    renderIde(fakeBuilder({ unsaved: true }));
    expect(await screen.findByText("Unsaved")).toBeInTheDocument();
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
    renderIde(fakeBuilder({ unsaved: true }));
    expect(await screen.findByText(/^Draft /)).toBeInTheDocument();
  });

  it("offers Save draft beside Save & update board while live, and saves the editor content as the draft", async () => {
    const calls = mockHub();
    const { onSaveActionsChange } = renderIde();
    await waitFor(() => expect(latestRenderer(onSaveActionsChange)).toBeDefined());
    const save = vi.fn();
    render(
      <>
        {latestRenderer(onSaveActionsChange)!({
          save,
          saving: false,
          disabled: false,
          size: "sm",
          compact: false,
          anchor: { "data-ai-anchor": "page-editor.save" },
        })}
      </>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Save & update board" }));
    expect(save).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
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
    const { onSaveActionsChange } = renderIde();
    await waitFor(() => expect(onSaveActionsChange).toHaveBeenLastCalledWith(undefined));
    const status = await waitFor(() => {
      const row = document.querySelector<HTMLElement>('[data-slot="preview-status"]');
      expect(row).toHaveAttribute("data-display", "not-scheduled");
      return row!;
    });
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
    const { onSaveActionsChange, rerenderTick } = renderIde();
    await waitFor(() => expect(latestRenderer(onSaveActionsChange)).toBeDefined());
    render(
      <>
        {latestRenderer(onSaveActionsChange)!({
          save: vi.fn(),
          saving: false,
          disabled: false,
          size: "sm",
          compact: false,
          anchor: {},
        })}
      </>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(calls.draftPut).toHaveLength(1));
    await screen.findByText(/^Draft /);
    act(() => rerenderTick(1));
    await waitFor(() => expect(calls.draftDelete).toEqual(["d1"]));
  });

  // BB-B-27: a page without a draft is the usual case, not a failed request:
  // the IDE reads the drafts list first and asks for no draft that isn't there.
  it("asks for no draft the hub doesn't hold, so opening a page logs no 404", async () => {
    const calls = mockHub();
    renderIde();
    await screen.findByText(/Showing on Den TV now/);
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(calls.draftGet).toBe(0);
  });

  it("keeps a draft saved elsewhere (phone, Restore) after the editor saves the page; the hub marks it stale", async () => {
    const calls = mockHub({
      draft: {
        page_id: PAGE,
        revision: "phone-1",
        via: "phone",
        saved_at: "2026-11-17T15:44:00Z",
        stale: false,
        content: { ...snapshot, type: "template", template: ["FROM THE PHONE"] },
      },
    });
    const { rerenderTick } = renderIde();
    await screen.findByText(/^Draft /);
    const reads = calls.draftGet;
    act(() => rerenderTick(1));
    // The IDE re-reads the draft (for its stale flag) instead of deleting it.
    await waitFor(() => expect(calls.draftGet).toBeGreaterThan(reads));
    expect(calls.draftDelete).toEqual([]);
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
    const { onSaveActionsChange } = renderIde();
    await screen.findByText(/^Draft /);
    await waitFor(() => expect(latestRenderer(onSaveActionsChange)).toBeDefined());
    render(
      <>
        {latestRenderer(onSaveActionsChange)!({
          save: vi.fn(),
          saving: false,
          disabled: false,
          size: "sm",
          compact: false,
          anchor: {},
        })}
      </>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
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
