import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { PageGridSelector } from "@/components/page-grid-selector";

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
