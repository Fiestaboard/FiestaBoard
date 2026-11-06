import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

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
    .map((button) => button.getAttribute("data-section-item"));
}

describe("Pages library search and sorting", () => {
  let previewIds: string[][];
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();
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

  it("searches saved content within the current device tab and makes no previews in list mode", async () => {
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

  it("sorts the visible pages by created and updated dates", async () => {
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByText("Alpha");
    await user.click(screen.getByRole("combobox", { name: "Sort pages" }));
    await user.click(await screen.findByRole("option", { name: "Newest created" }));
    expect(resultIds()).toEqual(["beta", "alpha"]);
    await user.click(screen.getByRole("combobox", { name: "Sort pages" }));
    await user.click(await screen.findByRole("option", { name: "Recently updated" }));
    expect(resultIds()).toEqual(["alpha", "beta"]);
  });

  it("retains query, sort, nondefault device tab and list preference after visiting an editor", async () => {
    const user = userEvent.setup();
    const view = renderLibrary();
    await user.click(await screen.findByRole("tab", { name: "Note" }));
    await user.type(screen.getByRole("searchbox", { name: "Search pages" }), "weather");
    await user.click(screen.getByRole("combobox", { name: "Sort pages" }));
    await user.click(await screen.findByRole("option", { name: "Newest created" }));
    await user.click(screen.getByRole("button", { name: /Note forecast/ }));
    expect(push).toHaveBeenCalledWith("/pages/edit/note");
    view.unmount();
    renderLibrary();
    expect(await screen.findByRole("tab", { name: "Note" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("searchbox", { name: "Search pages" })).toHaveValue("weather");
    expect(screen.getByRole("combobox", { name: "Sort pages" })).toHaveTextContent("Newest created");
    expect(screen.getByRole("button", { name: "List view" })).toHaveAttribute("aria-pressed", "true");
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
    expect(screen.getByRole("combobox", { name: "Sort pages" })).toHaveTextContent("Recently updated");
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

  it("falls back from a removed device tab and creates for the visible display", async () => {
    sessionStorage.setItem(
      "fiestaboard_pages_library_query",
      JSON.stringify({ text: "", sort: "name-asc", device: "panel" }),
    );
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByText("Alpha");
    expect(screen.getByRole("tab", { name: "Flagship" })).toHaveAttribute("aria-selected", "true");
    await user.click(screen.getByRole("button", { name: /New page/i }));
    expect(push).toHaveBeenCalledWith("/pages/new");
  });

  it("creates for the visible tab while a removed saved tab awaits page loading", async () => {
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
        expect(screen.getByRole("tab", { name: "Flagship" })).toHaveAttribute("aria-selected", "true"),
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
      await user.click(await screen.findByRole("option", { name: "Newest created" }));
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
      await user.click(screen.getByRole("button", { name: "Grid view" }));
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
      await user.click(screen.getByRole("button", { name: "Grid view" }));
      await waitFor(() => expect(errors).toHaveBeenCalledWith("Failed to fetch batch previews:", expect.anything()));
      expect(calls).toHaveBeenCalledTimes(1);
      await user.click(screen.getByRole("combobox", { name: "Sort pages" }));
      await user.click(await screen.findByRole("option", { name: "Newest created" }));
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
      await user.click(screen.getByRole("button", { name: "Grid view" }));
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
      await user.click(screen.getByRole("button", { name: "Grid view" }));
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

  it("restores an orphan device tab after delayed page data arrives", async () => {
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
    await waitFor(() => expect(screen.getByRole("tab", { name: "Note" })).toHaveAttribute("aria-selected", "true"));
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
