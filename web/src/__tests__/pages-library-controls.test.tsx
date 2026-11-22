import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { PageGridSelector } from "@/components/page-grid-selector";
import * as translations from "@/i18n/translations";
import { api } from "@/lib/api";

import PagesPage from "../../app/routes/pages._index";
import { server } from "./mocks/server";

const push = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push, replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
}));
vi.mock("@/components/smart-link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}));

const pages = [
  {
    id: "alpha",
    name: "Alpha",
    device_type: "flagship",
    template: ["{{weather.temp}}"],
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-03T00:00:00Z",
  },
  {
    id: "beta",
    name: "Beta",
    device_type: "flagship",
    template: ["{{stocks.price}}"],
    created_at: "2024-01-02T00:00:00Z",
    updated_at: null,
  },
  {
    id: "note",
    name: "Note forecast",
    device_type: "note",
    template: ["{{weather.temp}}"],
    created_at: "2024-01-03T00:00:00Z",
    updated_at: null,
  },
].map((page) => ({ ...page, type: "template", duration_seconds: 300 }));

function renderLibrary(children = <PagesPage />) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <CurrentBoardProvider>{children}</CurrentBoardProvider>
    </QueryClientProvider>,
  );
  return { ...view, client };
}

function resultIds() {
  return within(screen.getByRole("group", { name: "Pages" }))
    .getAllByRole("button")
    .filter((button) => button.hasAttribute("data-section-item"))
    .map((button) => button.getAttribute("data-section-item"));
}

describe("Pages library search and sorting", () => {
  let previewIds: string[][];
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();
    sessionStorage.setItem("fiestaboard_pages_display_filter", "board");
    localStorage.setItem("fiestaboard_pages_view_mode", "list");
    previewIds = [];
    server.use(
      http.get("/api/settings/board", () =>
        HttpResponse.json({
          board_type: "black",
          devices: ["flagship", "note"],
          boards: [
            { id: "board", name: "Main", device_type: "flagship", board_color: "black" },
            { id: "note-board", name: "Note", device_type: "note", board_color: "black" },
          ],
        }),
      ),
      http.get("/api/v1/pages", () => HttpResponse.json({ pages, total: pages.length })),
      http.get("/api/v1/collections", () => HttpResponse.json({ collections: [], total: 0 })),
      http.get("/api/panels", () => HttpResponse.json({ panels: [], total: 0 })),
      http.post("/api/pages/preview/batch", async ({ request }) => {
        previewIds.push(((await request.json()) as { page_ids: string[] }).page_ids);
        return HttpResponse.json({ previews: {}, total: 0, successful: 0 });
      }),
    );
  });

  it("searches saved content within the selected display and makes no previews in list mode", async () => {
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByText("Alpha");
    await user.type(screen.getByRole("searchbox", { name: "Search pages" }), "weather");
    expect(resultIds()).toEqual(["alpha"]);
    expect(screen.queryByText("Note forecast")).not.toBeInTheDocument();
    expect(previewIds).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Clear search" }));
    expect(resultIds()).toEqual(["alpha", "beta"]);
    expect(screen.getByRole("searchbox", { name: "Search pages" })).toHaveFocus();
  });

  it("reorders names when the active locale changes without changing the query", async () => {
    const locale = vi.spyOn(translations, "useLocale").mockReturnValue("en");
    const names = [
      ["z", "Zebra"],
      ["umlaut", "Ärende"],
      ["ring", "Åsa"],
      ["o", "Öl"],
    ];
    server.use(
      http.get("/api/v1/pages", () =>
        HttpResponse.json({ pages: names.map(([id, name]) => ({ ...pages[0], id, name })), total: names.length }),
      ),
    );
    const libraryQuery = { text: "", sort: "name-asc" as const };
    const onSelectPage = () => {};
    const selector = () => (
      <PageGridSelector
        onSelectPage={onSelectPage}
        showCollections={false}
        deviceTypeFilter="flagship"
        viewMode="list"
        libraryQuery={libraryQuery}
      />
    );
    try {
      const view = renderLibrary(selector());
      await waitFor(() => expect(resultIds()).toEqual(["umlaut", "ring", "o", "z"]));
      locale.mockReturnValue("sv");
      view.rerender(
        <QueryClientProvider client={view.client}>
          <CurrentBoardProvider>{selector()}</CurrentBoardProvider>
        </QueryClientProvider>,
      );
      await waitFor(() => expect(resultIds()).toEqual(["z", "ring", "umlaut", "o"]));
      expect(previewIds).toEqual([]);
    } finally {
      locale.mockRestore();
    }
  });

  it("keeps search and sort while switching between a display and All pages", async () => {
    sessionStorage.setItem("fiestaboard_pages_display_filter", "all");
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByText("Note forecast");
    await user.type(screen.getByRole("searchbox", { name: "Search pages" }), "weather");
    expect(resultIds()).toEqual(["alpha", "note"]);
    await user.click(screen.getByRole("combobox", { name: "Sort pages" }));
    await user.click(await screen.findByRole("option", { name: "Created, newest first" }));
    expect(resultIds()).toEqual(["note", "alpha"]);
    await user.click(screen.getByRole("combobox", { name: "Display filter" }));
    await user.click(await screen.findByRole("option", { name: "Note" }));
    expect(resultIds()).toEqual(["note"]);
    expect(screen.getByRole("searchbox", { name: "Search pages" })).toHaveValue("weather");
    expect(screen.getByRole("combobox", { name: "Sort pages" })).toHaveTextContent("Created, newest first");
    await user.click(screen.getByRole("button", { name: /New page/i }));
    expect(push).toHaveBeenCalledWith("/pages/new?board=note-board");
    await user.click(screen.getByRole("combobox", { name: "Display filter" }));
    await user.click(await screen.findByRole("option", { name: "All pages" }));
    expect(resultIds()).toEqual(["note", "alpha"]);
  });

  it("sorts the visible pages by created and updated dates", async () => {
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByText("Alpha");
    await user.click(screen.getByRole("combobox", { name: "Sort pages" }));
    await user.click(await screen.findByRole("option", { name: "Created, newest first" }));
    expect(resultIds()).toEqual(["beta", "alpha"]);
    await user.click(screen.getByRole("combobox", { name: "Sort pages" }));
    await user.click(await screen.findByRole("option", { name: "Updated, newest first" }));
    expect(resultIds()).toEqual(["alpha", "beta"]);
  });

  it("retains query, sort, nondefault display and list preference after visiting an editor", async () => {
    const user = userEvent.setup();
    const view = renderLibrary();
    await user.click(await screen.findByRole("combobox", { name: "Display filter" }));
    await user.click(await screen.findByRole("option", { name: "Note" }));
    await user.type(screen.getByRole("searchbox", { name: "Search pages" }), "weather");
    await user.click(screen.getByRole("combobox", { name: "Sort pages" }));
    await user.click(await screen.findByRole("option", { name: "Created, newest first" }));
    await user.click(screen.getByRole("button", { name: /^Note forecast/ }));
    expect(push).toHaveBeenCalledWith("/pages/edit/note");
    view.unmount();
    renderLibrary();
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Display filter" })).toHaveTextContent("Note"));
    expect(screen.getByRole("searchbox", { name: "Search pages" })).toHaveValue("weather");
    expect(screen.getByRole("combobox", { name: "Sort pages" })).toHaveTextContent("Created, newest first");
    expect(screen.getByRole("radio", { name: "List" })).toHaveAttribute("aria-checked", "true");
    expect(await screen.findByText("Note forecast")).toBeInTheDocument();
    expect(screen.queryByText("Alpha")).not.toBeInTheDocument();
  });

  it("explains no matches and can clear the search without claiming the library is empty", async () => {
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByText("Alpha");
    await user.type(screen.getByRole("searchbox", { name: "Search pages" }), "not-present");
    expect(screen.getByText("No matching pages")).toBeInTheDocument();
    expect(screen.queryByText("No pages created yet.")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear search" }));
    expect(screen.getByText("Alpha")).toBeInTheDocument();
  });

  it("keeps the search and offers retry when saved pages cannot load", async () => {
    sessionStorage.setItem(
      "fiestaboard_pages_library_query",
      JSON.stringify({ text: "weather", sort: "updated-desc", device: "flagship" }),
    );
    server.use(http.get("/api/v1/pages", () => HttpResponse.json({ detail: "unavailable" }, { status: 503 })));
    const user = userEvent.setup();
    renderLibrary();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load pages");
    expect(screen.queryByText("No matching pages")).not.toBeInTheDocument();
    expect(screen.queryByText("No pages created yet.")).not.toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Search pages" })).toHaveValue("weather");
    server.use(http.get("/api/v1/pages", () => HttpResponse.json({ pages, total: pages.length })));
    await user.click(screen.getByRole("button", { name: "Retry loading pages" }));
    expect(await screen.findByText("Alpha")).toBeInTheDocument();
    expect(screen.queryByText("Beta")).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Sort pages" })).toHaveTextContent("Updated, newest first");
  });

  it("retains loaded pages and the query after a failed background page refetch", async () => {
    const user = userEvent.setup();
    const view = renderLibrary();
    await screen.findByText("Alpha");
    await user.type(screen.getByRole("searchbox", { name: "Search pages" }), "weather");
    const data = view.client.getQueryData(["pages"]);
    server.use(http.get("/api/v1/pages", () => new HttpResponse(null, { status: 503 })));
    await act(async () => {
      await view.client.refetchQueries({ queryKey: ["pages"] });
      // React Query schedules observer notifications after the cache settles.
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(view.client.getQueryState(["pages"])?.status).toBe("error");
    expect(view.client.getQueryData(["pages"])).toBe(data);
    expect(screen.queryByText("Alpha")).toBeInTheDocument();
    expect(screen.queryByText("Beta")).not.toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Search pages" })).toHaveValue("weather");
    expect(resultIds()).toEqual(["alpha"]);
  });

  it("falls back from a removed display and creates for the visible display", async () => {
    sessionStorage.setItem("fiestaboard_pages_display_filter", "removed-board");
    sessionStorage.setItem(
      "fiestaboard_pages_library_query",
      JSON.stringify({ text: "", sort: "name-asc", device: "panel" }),
    );
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByText("Alpha");
    expect(screen.getByRole("combobox", { name: "Display filter" })).toHaveTextContent("All pages");
    await user.click(screen.getByRole("button", { name: /New page/i }));
    expect(push).toHaveBeenCalledWith("/pages/new");
  });

  it("creates for the current display while a removed saved display awaits page loading", async () => {
    sessionStorage.setItem("fiestaboard_pages_display_filter", "removed-board");
    sessionStorage.setItem(
      "fiestaboard_pages_library_query",
      JSON.stringify({ text: "", sort: "name-asc", device: "panel" }),
    );
    let release!: () => void;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.get("/api/v1/pages", async () => {
        await pending;
        return HttpResponse.json({ pages });
      }),
    );
    const user = userEvent.setup();
    renderLibrary();
    try {
      await waitFor(() =>
        expect(screen.getByRole("combobox", { name: "Display filter" })).toHaveTextContent("All pages"),
      );
      await user.click(screen.getByRole("button", { name: /New page/i }));
      expect(push).toHaveBeenCalledWith("/pages/new");
    } finally {
      release();
    }
  });

  it("reuses a pending preview batch across typing and sorting", async () => {
    localStorage.setItem("fiestaboard_pages_view_mode", "grid");
    let release!: () => void;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.post("/api/pages/preview/batch", async ({ request }) => {
        previewIds.push(((await request.json()) as { page_ids: string[] }).page_ids);
        await pending;
        return HttpResponse.json({
          previews: Object.fromEntries(
            pages.map((p) => [p.id, { page_id: p.id, available: true, message: "SAMPLE", lines: ["SAMPLE"] }]),
          ),
        });
      }),
    );
    const user = userEvent.setup();
    renderLibrary();
    try {
      await screen.findByText("Alpha");
      await waitFor(() => expect(previewIds).toEqual([["alpha", "beta"]]));
      await user.type(screen.getByRole("searchbox", { name: "Search pages" }), "weather");
      await user.click(screen.getByRole("combobox", { name: "Sort pages" }));
      await user.click(await screen.findByRole("option", { name: "Created, newest first" }));
      expect(previewIds).toEqual([["alpha", "beta"]]);
    } finally {
      release();
    }
    await waitFor(() => expect(localStorage.getItem("fiestaboard_previews_batch")).toContain("SAMPLE"));
  });

  it.each([
    ["http", "edit"],
    ["network", "edit"],
    ["http", "refetch"],
    ["network", "refetch"],
  ] as const)("retries a failed %s preview batch after a page-list %s", async (failure, retry) => {
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    const user = userEvent.setup();
    server.use(
      http.post("/api/pages/preview/batch", async ({ request }) => {
        const ids = ((await request.json()) as { page_ids: string[] }).page_ids;
        previewIds.push(ids);
        if (previewIds.length === 1) {
          return failure === "http" ? new HttpResponse(null, { status: 503 }) : HttpResponse.error();
        }
        return HttpResponse.json({
          previews: Object.fromEntries(
            ids.map((id) => [id, { page_id: id, available: true, message: "RECOVERED", lines: ["RECOVERED"] }]),
          ),
        });
      }),
    );
    try {
      const view = renderLibrary();
      await screen.findByText("Alpha");
      await user.click(screen.getByRole("radio", { name: "Grid" }));
      await waitFor(() => expect(errors).toHaveBeenCalledWith("Failed to fetch batch previews:", expect.anything()));
      expect(previewIds).toEqual([["alpha", "beta"]]);
      if (retry === "edit") {
        act(() =>
          view.client.setQueryData(["pages"], {
            pages: pages.map((page) => (page.id === "beta" ? { ...page, name: "Beta edited" } : page)),
          }),
        );
      } else {
        const data = view.client.getQueryData(["pages"]);
        await act(async () => {
          await view.client.refetchQueries({ queryKey: ["pages"] });
        });
        expect(view.client.getQueryData(["pages"])).toBe(data);
      }
      await waitFor(() =>
        expect(previewIds).toEqual([
          ["alpha", "beta"],
          ["alpha", "beta"],
        ]),
      );
      await waitFor(() => expect(localStorage.getItem("fiestaboard_previews_batch")).toContain("RECOVERED"));
    } finally {
      errors.mockRestore();
    }
  });

  it("does not retry a failed batch for query-only sorting and typing", async () => {
    const calls = vi.spyOn(api, "previewPagesBatch");
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    server.use(
      http.get("/api/v1/pages", () =>
        HttpResponse.json({
          pages: pages.map((page) => ({ ...page, name: `Artwork ${page.name}` })),
          total: pages.length,
        }),
      ),
      http.post("/api/pages/preview/batch", () => new HttpResponse(null, { status: 503 })),
    );
    try {
      const user = userEvent.setup();
      renderLibrary();
      await screen.findByText("Artwork Alpha");
      await user.click(screen.getByRole("radio", { name: "Grid" }));
      await waitFor(() => expect(errors).toHaveBeenCalledWith("Failed to fetch batch previews:", expect.anything()));
      expect(calls).toHaveBeenCalledTimes(1);
      await user.click(screen.getByRole("combobox", { name: "Sort pages" }));
      await user.click(await screen.findByRole("option", { name: "Created, newest first" }));
      await user.type(screen.getByRole("searchbox", { name: "Search pages" }), "ar");
      await act(async () => {
        await Promise.allSettled(
          calls.mock.results.map((result) => (result.type === "return" ? result.value : undefined)),
        );
      });
      expect(calls).toHaveBeenCalledTimes(1);
    } finally {
      calls.mockRestore();
      errors.mockRestore();
    }
  });

  it("does not retry on typing when a pending batch fails after a page refetch", async () => {
    const calls = vi.spyOn(api, "previewPagesBatch");
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    let release!: () => void;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.get("/api/v1/pages", () =>
        HttpResponse.json({
          pages: pages.map((page) => ({ ...page, name: `Artwork ${page.name}` })),
          total: pages.length,
        }),
      ),
      http.post("/api/pages/preview/batch", async () => {
        await pending;
        return new HttpResponse(null, { status: 503 });
      }),
    );
    try {
      const user = userEvent.setup();
      const view = renderLibrary();
      await screen.findByText("Artwork Alpha");
      await user.click(screen.getByRole("radio", { name: "Grid" }));
      await waitFor(() => expect(calls).toHaveBeenCalledTimes(1));
      const data = view.client.getQueryData(["pages"]);
      const updatedAt = view.client.getQueryState(["pages"])!.dataUpdatedAt;
      await act(async () => {
        await view.client.refetchQueries({ queryKey: ["pages"] });
        // Deliver the completed refetch to observers before the batch fails.
        await new Promise((resolve) => setTimeout(resolve, 0));
      });
      expect(view.client.getQueryState(["pages"])!.dataUpdatedAt).toBeGreaterThan(updatedAt);
      expect(view.client.getQueryData(["pages"])).toBe(data);
      await act(async () => {
        release();
        await Promise.allSettled(calls.mock.results.map((result) => result.value));
      });
      await waitFor(() => expect(errors).toHaveBeenCalled());
      await user.type(screen.getByRole("searchbox", { name: "Search pages" }), "ar");
      await act(async () => {
        await Promise.allSettled(calls.mock.results.map((result) => result.value));
      });
      expect(calls).toHaveBeenCalledTimes(1);
    } finally {
      release();
      calls.mockRestore();
      errors.mockRestore();
    }
  });

  it("revalidates a temporarily unavailable page after unchanged page data refetches", async () => {
    const calls = vi.spyOn(api, "previewPagesBatch");
    let recovered = false;
    server.use(
      http.post("/api/pages/preview/batch", async ({ request }) => {
        const ids = ((await request.json()) as { page_ids: string[] }).page_ids;
        return HttpResponse.json({
          previews: Object.fromEntries(
            ids.map((id) => [
              id,
              recovered
                ? { page_id: id, available: true, message: "RECOVERED", lines: ["RECOVERED"] }
                : { available: false, error: "Temporarily unavailable" },
            ]),
          ),
        });
      }),
    );
    try {
      const user = userEvent.setup();
      const view = renderLibrary();
      await screen.findByText("Alpha");
      await user.click(screen.getByRole("radio", { name: "Grid" }));
      await waitFor(() => expect(calls).toHaveBeenCalledTimes(1));
      await act(async () => {
        await calls.mock.results[0].value;
      });
      recovered = true;
      const data = view.client.getQueryData(["pages"]);
      await act(async () => {
        await view.client.refetchQueries({ queryKey: ["pages"] });
      });
      expect(view.client.getQueryData(["pages"])).toBe(data);
      await waitFor(() => expect(calls).toHaveBeenCalledTimes(2));
      await waitFor(() => expect(localStorage.getItem("fiestaboard_previews_batch")).toContain("RECOVERED"));
    } finally {
      calls.mockRestore();
    }
  });

  it("does not reuse or overwrite a newer preview when an older revision finishes late", async () => {
    let release!: () => void;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.post("/api/pages/preview/batch", async ({ request }) => {
        const ids = ((await request.json()) as { page_ids: string[] }).page_ids;
        previewIds.push(ids);
        const old = previewIds.length === 1;
        if (old) await pending;
        return HttpResponse.json({
          previews: {
            alpha: { page_id: "alpha", available: true, message: old ? "OLD" : "NEW", lines: [old ? "OLD" : "NEW"] },
          },
        });
      }),
    );
    const view = renderLibrary(
      <PageGridSelector
        onSelectPage={() => {}}
        showCollections={false}
        deviceTypeFilter="flagship"
        libraryQuery={{ text: "weather", sort: "name-asc" }}
      />,
    );
    try {
      await waitFor(() => expect(previewIds).toEqual([["alpha"]]));
      act(() =>
        view.client.setQueryData(["pages"], {
          pages: pages.map((page) => (page.id === "alpha" ? { ...page, updated_at: "2024-02-01T00:00:00Z" } : page)),
        }),
      );
      await waitFor(() => expect(previewIds).toEqual([["alpha"], ["alpha"]]));
      await waitFor(() => expect(localStorage.getItem("fiestaboard_previews_batch")).toContain("NEW"));
    } finally {
      release();
    }
    await act(async () => {
      await pending;
    });
    expect(localStorage.getItem("fiestaboard_previews_batch")).not.toContain("OLD");
  });

  it("keeps an unavailable preview result when the search changes", async () => {
    localStorage.setItem("fiestaboard_pages_view_mode", "grid");
    server.use(
      http.post("/api/pages/preview/batch", async ({ request }) => {
        const ids = ((await request.json()) as { page_ids: string[] }).page_ids;
        previewIds.push(ids);
        return HttpResponse.json({
          previews: Object.fromEntries(ids.map((id) => [id, { available: false, error: "Unavailable" }])),
        });
      }),
    );
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByText("Alpha");
    await waitFor(() => expect(previewIds).toEqual([["alpha", "beta"]]));
    await user.type(screen.getByRole("searchbox", { name: "Search pages" }), "weather");
    await user.click(screen.getByRole("button", { name: "Clear search" }));
    expect(previewIds).toEqual([["alpha", "beta"]]);
  });

  it("keeps orphan pages searchable in All pages after delayed page data arrives", async () => {
    sessionStorage.setItem("fiestaboard_pages_display_filter", "all");
    sessionStorage.setItem(
      "fiestaboard_pages_library_query",
      JSON.stringify({ text: "weather", sort: "name-asc", device: "note" }),
    );
    let release!: () => void;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.get("/api/settings/board", () =>
        HttpResponse.json({
          board_type: "black",
          devices: ["flagship"],
          boards: [{ id: "board", name: "Main", device_type: "flagship", board_color: "black" }],
        }),
      ),
      http.get("/api/v1/pages", async () => {
        await pending;
        return HttpResponse.json({ pages, total: pages.length });
      }),
    );
    renderLibrary();
    await screen.findByRole("searchbox", { name: "Search pages" });
    release();
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: "Display filter" })).toHaveTextContent("All pages"),
    );
    expect(await screen.findByText("Note forecast")).toBeInTheDocument();
  });

  it("uses safe defaults for malformed stored query state", async () => {
    sessionStorage.setItem("fiestaboard_pages_library_query", '{"text":[],"sort":"unknown","device":"unknown"}');
    renderLibrary();
    await screen.findByText("Alpha");
    expect(screen.getByRole("searchbox", { name: "Search pages" })).toHaveValue("");
    expect(screen.getByRole("combobox", { name: "Sort pages" })).toHaveTextContent("Name A–Z");
  });

  it("filters before requesting grid previews while an ordinary picker still shows all compatible pages", async () => {
    localStorage.setItem("fiestaboard_pages_view_mode", "grid");
    const view = renderLibrary(
      <PageGridSelector
        onSelectPage={() => {}}
        showCollections={false}
        deviceTypeFilter="flagship"
        libraryQuery={{ text: "weather", sort: "name-asc" }}
      />,
    );
    expect(await screen.findByText("Alpha")).toBeInTheDocument();
    expect(screen.queryByText("Beta")).not.toBeInTheDocument();
    await waitFor(() => expect(previewIds).toEqual([["alpha"]]));
    view.unmount();
    renderLibrary(
      <PageGridSelector onSelectPage={() => {}} showCollections={false} deviceTypeFilter="flagship" viewMode="list" />,
    );
    expect(await screen.findByText("Beta")).toBeInTheDocument();
  });
});

// BB-FP-2 (Figma 297:1824 PageCard): the board full-bleed on top, then a meta
// block with the title, "<display> · <model> <size>" and "Edited … · Schedule …",
// a Now showing badge on the page on screen, three columns on a wide screen.
describe("Pages library card", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();
    localStorage.setItem("fiestaboard_pages_view_mode", "grid");
    server.use(
      http.get("/api/settings/board", () =>
        HttpResponse.json({
          board_type: "black",
          devices: ["flagship"],
          boards: [{ id: "board", name: "Main", device_type: "flagship", board_color: "black" }],
        }),
      ),
      http.get("/api/v1/pages", () => HttpResponse.json({ pages: pages.slice(0, 2), total: 2 })),
      http.get("/api/v1/collections", () => HttpResponse.json({ collections: [], total: 0 })),
      http.get("/api/panels", () => HttpResponse.json({ panels: [], total: 0 })),
      http.post("/api/pages/preview/batch", () => HttpResponse.json({ previews: {}, total: 0, successful: 0 })),
      http.get("/api/v1/schedules", () =>
        HttpResponse.json({
          schedules: [{ id: "s1", page_id: "beta", start_time: "07:00", end_time: "09:00", enabled: true }],
          total: 1,
        }),
      ),
      http.get("/api/v1/boards/:board", ({ params }) =>
        HttpResponse.json({ id: params.board, active_page_id: "alpha", resolved_page_id: "alpha", paused: false }),
      ),
      http.get("/api/schedules/active/page", () =>
        HttpResponse.json({
          page_id: "alpha",
          temporary_override: { active: false, page_id: null, expires_at: null, remaining_seconds: null },
        }),
      ),
    );
  });

  function card(name: string) {
    return screen.getByText(name, { selector: "[data-card-meta] span" }).closest("button")!;
  }

  it("draws the board first, then the title and two meta lines", async () => {
    renderLibrary();
    await screen.findByText("Alpha");
    const alpha = card("Alpha");
    expect(alpha.firstElementChild).toHaveAttribute("data-card-preview");
    const meta = alpha.querySelector<HTMLElement>("[data-card-meta]")!;
    expect(meta).toHaveTextContent(/Main\s*·\s*Flagship\s*22\s*×\s*6/);
    expect(meta).toHaveTextContent(/Edited /);
    await waitFor(() => expect(card("Beta").querySelector("[data-card-meta]")).toHaveTextContent(/Schedule 7:00/));
  });

  // FABLE-2608 M1: a page never edited since it was made reads its creation
  // time (the hub sets updated_at only on an update).
  it("dates a never-edited page by when it was created", async () => {
    renderLibrary();
    await screen.findByText("Beta");
    await waitFor(() =>
      expect(card("Beta").querySelector("[data-card-meta]")).toHaveTextContent(/Edited .+ · Schedule 7:00/),
    );
  });

  it("badges the page on screen as Now showing", async () => {
    renderLibrary();
    await screen.findByText("Alpha");
    await waitFor(() => expect(within(card("Alpha")).getByText("Now showing")).toBeInTheDocument());
    expect(within(card("Beta")).queryByText("Now showing")).not.toBeInTheDocument();
  });

  it("lays the cards out three across on a wide screen", async () => {
    renderLibrary();
    await screen.findByText("Alpha");
    expect(screen.getByRole("group", { name: "Pages" })).toHaveClass("xl:grid-cols-3");
  });
});

// BB-FP-6 / BB-FP-7 / BB-FP-8 (Figma 297:1824, 303:16324): the library toolbar.
describe("Pages library toolbar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();
    localStorage.setItem("fiestaboard_pages_view_mode", "list");
    server.use(
      http.get("/api/settings/board", () =>
        HttpResponse.json({ board_type: "black", devices: ["flagship"], boards: [] }),
      ),
      http.get("/api/v1/pages", () => HttpResponse.json({ pages, total: pages.length })),
      http.get("/api/v1/collections", () => HttpResponse.json({ collections: [], total: 0 })),
      http.get("/api/panels", () => HttpResponse.json({ panels: [], total: 0 })),
    );
  });

  it("switches Grid / List with a text segmented control and imports from an outline button", async () => {
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByText("Alpha");
    const view = screen.getByRole("radiogroup", { name: "View mode" });
    expect(view).toHaveAttribute("data-slot", "segmented-control");
    const grid = within(view).getByRole("radio", { name: "Grid" });
    const list = within(view).getByRole("radio", { name: "List" });
    expect(grid).toHaveTextContent("Grid");
    expect(list).toHaveTextContent("List");
    expect(list).toHaveAttribute("aria-checked", "true");
    await user.click(grid);
    expect(grid).toHaveAttribute("aria-checked", "true");
    expect(localStorage.getItem("fiestaboard_pages_view_mode")).toBe("grid");

    const importButton = screen.getByRole("button", { name: "Import" });
    expect(importButton).toHaveAttribute("data-variant", "outline");
    expect(importButton.querySelector("svg")).toBeNull();
  });

  it("searches from a 'Search pages' field with an in-field clear and no standing help text", async () => {
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByText("Alpha");
    const search = screen.getByRole("searchbox", { name: "Search pages" });
    expect(search).toHaveAttribute("placeholder", "Search pages");
    expect(screen.queryByText(/Searches names and saved content/)).not.toBeInTheDocument();
    expect(screen.queryByText(/of \d+ pages/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Clear search" })).not.toBeInTheDocument();

    await user.type(search, "zzzz");
    expect(screen.getByText("No matching pages")).toBeInTheDocument();
    expect(screen.getAllByText(/Searches names and saved content/)).toHaveLength(1);
    const clear = screen.getByRole("button", { name: "Clear search" });
    // The clear control sits inside the field, as an icon (no text label).
    expect(clear).not.toHaveTextContent(/\S/);
    // A kit icon size that grows to the 44 px touch target on a coarse pointer.
    expect(clear).toHaveAttribute("data-size", "icon-sm");
    expect(search.parentElement).toContainElement(clear);
    await user.click(clear);
    expect(search).toHaveValue("");
    expect(search).toHaveFocus();
  });

  it("offers parallel sort labels", async () => {
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByText("Alpha");
    await user.click(screen.getByRole("combobox", { name: "Sort pages" }));
    const options = (await screen.findAllByRole("option")).map((o) => o.textContent);
    expect(options).toEqual([
      "Name A–Z",
      "Name Z–A",
      "Created, newest first",
      "Created, oldest first",
      "Updated, newest first",
      "Updated, oldest first",
    ]);
  });
});

// BB-B-8 (Figma 303:18724): each card has a menu to edit, duplicate or delete
// the page without opening it.
describe("Pages library card menu", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();
    localStorage.setItem("fiestaboard_pages_view_mode", "list");
    server.use(
      http.get("/api/settings/board", () =>
        HttpResponse.json({
          board_type: "black",
          devices: ["flagship"],
          boards: [{ id: "board", name: "Main", device_type: "flagship", board_color: "black", paused: false }],
        }),
      ),
      http.get("/api/v1/pages", () => HttpResponse.json({ pages, total: pages.length })),
      http.get("/api/v1/collections", () => HttpResponse.json({ collections: [], total: 0 })),
      http.get("/api/panels", () => HttpResponse.json({ panels: [], total: 0 })),
    );
  });

  afterEach(() => vi.unstubAllGlobals());

  function stubCoarsePointer() {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query === "(pointer: coarse)",
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
  }

  function menuItemNames() {
    return screen.getAllByRole("menuitem").map((item) => item.textContent);
  }

  // BB-FP-3 (Figma 299:6080): a label with the page's name, then Edit (E) ·
  // Change Page… · Add to Schedule · Duplicate (⌘D) · Export share string │
  // Pause <display>. Delete lives in the phone's sheet (303:18724) and the editor.
  it("lists Figma's desktop items under the page's name, with shortcuts and no Delete", async () => {
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByText("Alpha");
    await user.click(screen.getByRole("button", { name: "Actions for Alpha" }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByText("Alpha", { selector: "[data-slot=dropdown-menu-label]" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Edit" })).toHaveAttribute("aria-keyshortcuts", "E");
    expect(screen.getByRole("menuitem", { name: "Duplicate" })).toHaveAttribute(
      "aria-keyshortcuts",
      expect.stringMatching(/^(Meta|Control)\+D$/),
    );
    expect(menuItemNames()).toEqual([
      "EditE",
      "Change Page…",
      "Add to Schedule",
      expect.stringMatching(/^Duplicate(⌘D|Ctrl\+D)$/),
      "Export share string",
      "Pause Main",
    ]);
  });

  it("keeps Delete and drops Pause and the shortcut letters on a coarse pointer (Figma 303:18724)", async () => {
    stubCoarsePointer();
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByText("Alpha");
    await user.click(screen.getByRole("button", { name: "Actions for Alpha" }));
    await screen.findByRole("menu");
    expect(menuItemNames()).toEqual([
      "Edit",
      "Change Page…",
      "Add to Schedule",
      "Duplicate",
      "Export share string",
      "Delete page…",
    ]);
  });

  it("exports the page's share string from its card", async () => {
    server.use(
      http.get("/api/pages/:id/share", ({ params }) => HttpResponse.json({ share_string: `FB1:${params.id}` })),
    );
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByText("Alpha");
    await user.click(screen.getByRole("button", { name: "Actions for Alpha" }));
    await user.click(await screen.findByRole("menuitem", { name: "Export share string" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("textbox", { name: "Share string" })).toHaveValue("FB1:alpha");
  });

  it("pauses the current display from a card", async () => {
    const patched: unknown[] = [];
    server.use(
      http.patch("/api/v1/boards/:id", async ({ params, request }) => {
        patched.push([params.id, await request.json()]);
        return HttpResponse.json({ id: params.id, paused: true });
      }),
    );
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByText("Alpha");
    await user.click(screen.getByRole("button", { name: "Actions for Alpha" }));
    await user.click(await screen.findByRole("menuitem", { name: "Pause Main" }));
    await waitFor(() => expect(patched).toEqual([["board", { paused: true }]]));
  });

  it("opens Show now for the page from Change Page…", async () => {
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByText("Alpha");
    await user.click(screen.getByRole("button", { name: "Actions for Alpha" }));
    await user.click(await screen.findByRole("menuitem", { name: "Change Page…" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  // FABLE-2603 M1: Change Page… shows the page on the current display, so a
  // page drawn for another size has no Change Page… (nothing to send it to).
  it("offers no Change Page… for a page that does not fit the current display", async () => {
    server.use(
      http.get("/api/v1/pages", () =>
        HttpResponse.json({
          pages: [...pages, { ...pages[0], id: "notey", name: "Notey", device_type: "note" }],
          total: pages.length + 1,
        }),
      ),
    );
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByText("Notey");
    await user.click(screen.getByRole("button", { name: "Actions for Notey" }));
    await screen.findByRole("menu");
    expect(screen.queryByRole("menuitem", { name: "Change Page…" })).not.toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Edit" })).toBeInTheDocument();
  });

  it("edits with E and duplicates with Mod+D from a focused card", async () => {
    const duplicated: string[] = [];
    server.use(
      http.post("/api/pages/:id/duplicate", ({ params }) => {
        duplicated.push(String(params.id));
        return HttpResponse.json(
          { page: { ...pages[0], id: "alpha-2", name: "Alpha copy" }, report: {} },
          { status: 201 },
        );
      }),
    );
    renderLibrary();
    const card = (await screen.findByText("Alpha")).closest("button")!;
    card.focus();
    fireEvent.keyDown(card, { key: "d", ctrlKey: true });
    await waitFor(() => expect(duplicated).toEqual(["alpha"]));
    fireEvent.keyDown(card, { key: "e" });
    expect(push).toHaveBeenCalledWith("/pages/edit/alpha");
  });

  it("edits and duplicates a page from its card", async () => {
    const duplicated: string[] = [];
    server.use(
      http.post("/api/pages/:id/duplicate", ({ params }) => {
        duplicated.push(String(params.id));
        return HttpResponse.json(
          { page: { ...pages[0], id: "alpha-2", name: "Alpha copy" }, report: {} },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByText("Alpha");

    await user.click(screen.getByRole("button", { name: "Actions for Alpha" }));
    await user.click(await screen.findByRole("menuitem", { name: "Edit" }));
    expect(push).toHaveBeenCalledWith("/pages/edit/alpha");

    await user.click(screen.getByRole("button", { name: "Actions for Alpha" }));
    await user.click(await screen.findByRole("menuitem", { name: "Duplicate" }));
    await waitFor(() => expect(duplicated).toEqual(["alpha"]));
  });

  it("deletes a page from its card on a coarse pointer", async () => {
    const deleted: string[] = [];
    server.use(
      http.delete("/api/v1/pages/:id", ({ params }) => {
        deleted.push(String(params.id));
        return HttpResponse.json({ status: "deleted" });
      }),
    );
    stubCoarsePointer();
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByText("Alpha");
    await user.click(screen.getByRole("button", { name: "Actions for Beta" }));
    await user.click(await screen.findByRole("menuitem", { name: "Delete page…" }));
    const confirm = await screen.findByRole("alertdialog");
    await user.click(within(confirm).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(deleted).toEqual(["beta"]));
  });

  it("opens the same menu from the card itself (right-click; long-press on touch) without opening the page", async () => {
    renderLibrary();
    const card = (await screen.findByText("Alpha")).closest("button")!;
    fireEvent.contextMenu(card);
    expect(await screen.findByRole("menuitem", { name: "Duplicate" })).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("moves focus to the next card's menu after a delete", async () => {
    let remaining = pages;
    server.use(
      http.get("/api/v1/pages", () => HttpResponse.json({ pages: remaining, total: remaining.length })),
      http.delete("/api/v1/pages/:id", ({ params }) => {
        remaining = remaining.filter((p) => p.id !== params.id);
        return HttpResponse.json({ status: "deleted" });
      }),
    );
    stubCoarsePointer();
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByText("Alpha");
    await user.click(screen.getByRole("button", { name: "Actions for Alpha" }));
    await user.click(await screen.findByRole("menuitem", { name: "Delete page…" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.queryByText("Alpha")).not.toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole("button", { name: "Actions for Beta" })).toHaveFocus());
  });
});
