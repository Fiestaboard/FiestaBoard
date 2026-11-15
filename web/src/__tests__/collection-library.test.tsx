import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Collection, Page } from "@/lib/api";

import { CollectionForm } from "../../app/routes/collections";
import CollectionsPage from "../../app/routes/collections._index";
import { server } from "./mocks/server";
const push = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-view-transition", () => ({ useViewTransition: () => ({ push }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const pages = [
  { id: "p1", name: "First", device_type: "flagship" },
  { id: "p2", name: "Second", device_type: "flagship" },
] as Page[];
const collection = {
  id: "collection:rotation",
  name: "Rotation",
  page_ids: ["p1", "p2"],
  selection_mode: "time",
  time: { interval_seconds: 5400 },
  variable: null,
  random: null,
  created_at: "2026-01-01",
} as Collection;
function renderLibrary() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <CollectionsPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}
describe("Collections library", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    vi.clearAllMocks();
    server.use(
      http.get("/api/v1/collections", () => HttpResponse.json({ collections: [collection] })),
      http.get("/api/v1/pages", () => HttpResponse.json({ pages })),
      http.post("/api/pages/preview/batch", () => HttpResponse.json({ previews: {} })),
    );
  });
  it("persists list mode across a remount without mounting page previews", async () => {
    const user = userEvent.setup();
    const first = renderLibrary();
    await user.click(await screen.findByRole("button", { name: "List view" }));
    expect(screen.getByRole("button", { name: "List view" })).toHaveAttribute("aria-pressed", "true");
    first.unmount();
    renderLibrary();
    await screen.findByText("Rotation");
    expect(screen.getByRole("button", { name: "List view" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByTestId("collection-page-stack")).not.toBeInTheDocument();
  });
  it("opens the collection's own detail route", async () => {
    const user = userEvent.setup();
    renderLibrary();
    await user.click(await screen.findByRole("button", { name: /Rotation/ }));
    expect(push).toHaveBeenCalledWith("/collections/collection%3Arotation");
  });
  it("reorders pages from the keyboard and preserves custom duration", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<CollectionForm collection={collection} pages={pages} onSubmit={onSubmit} onCancel={vi.fn()} />);
    const second = screen.getAllByRole("listitem").find((row) => row.textContent?.includes("Second"))!;
    second.focus();
    await user.keyboard(" {ArrowUp} ");
    expect(screen.getByRole("status")).toHaveTextContent("Second dropped · position 1 of 2");
    await user.click(screen.getByRole("button", { name: "Update Collection" }));
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({ page_ids: ["p2", "p1"], time: { interval_seconds: 5400 } }),
      ),
    );
  });
  it("reorders pages with Move up and saves the new order", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<CollectionForm collection={collection} pages={pages} onSubmit={onSubmit} onCancel={vi.fn()} />);
    const second = screen.getAllByRole("listitem").find((row) => row.textContent?.includes("Second"))!;
    await user.click(within(second).getByRole("button", { name: "Move up" }));
    await user.click(screen.getByRole("button", { name: "Update Collection" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ page_ids: ["p2", "p1"] })));
  });
  it("saves a non-adjacent pointer drop in the new order", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const three = [...pages, { id: "p3", name: "Third", device_type: "flagship" }] as Page[];
    render(
      <CollectionForm
        collection={{ ...collection, page_ids: ["p1", "p2", "p3"] }}
        pages={three}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
      />,
    );
    const items = Array.from(document.querySelectorAll<HTMLElement>('[data-slot="sortable-list-item"]'));
    const root = document.querySelector<HTMLElement>('[data-slot="sortable-list"]')!;
    root.getBoundingClientRect = () => DOMRect.fromRect({ x: 0, y: 100, width: 400, height: 216 });
    items.forEach((row, i) => {
      row.getBoundingClientRect = () => DOMRect.fromRect({ x: 0, y: 100 + i * 72, width: 400, height: 64 });
    });
    const handle = items[2].querySelector<HTMLElement>('[data-slot="sortable-list-handle"]')!;
    fireEvent.pointerDown(handle, { button: 0, pointerId: 1, clientY: 276 });
    fireEvent.pointerMove(handle, { pointerId: 1, clientY: 110 });
    fireEvent.pointerUp(handle, { pointerId: 1, clientY: 110 });
    await user.click(screen.getByRole("button", { name: "Update Collection" }));
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ page_ids: ["p3", "p1", "p2"] })),
    );
  });
  it("words the hint for touch on a coarse pointer, whatever the width", () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query === "(pointer: coarse)",
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    try {
      render(<CollectionForm collection={collection} pages={pages} onSubmit={vi.fn()} onCancel={vi.fn()} />);
      expect(screen.getByText(/Drag the handle, or use ··· › Move up \/ Move down\./)).toBeInTheDocument();
      expect(screen.queryByText(/focus a row and press Space/)).not.toBeInTheDocument();
    } finally {
      vi.unstubAllGlobals();
    }
  });
  it("words the hint for the keyboard on a fine pointer, whatever the width", () => {
    render(<CollectionForm collection={collection} pages={pages} onSubmit={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByText(/focus a row and press Space to lift it/)).toBeInTheDocument();
    expect(screen.queryByText(/Drag the handle, or use/)).not.toBeInTheDocument();
  });
  it("leaves the HTML5 drag API behind for the page list", () => {
    render(<CollectionForm collection={collection} pages={pages} onSubmit={vi.fn()} onCancel={vi.fn()} />);
    expect(document.querySelector('[data-slot="sortable-list"] [draggable]')).toBeNull();
    expect(document.querySelector('[data-slot="sortable-list"]')).not.toBeNull();
  });
});
