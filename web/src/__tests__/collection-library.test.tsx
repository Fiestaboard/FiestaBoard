import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
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
  it("reorders pages with keyboard-operable controls and preserves custom duration", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<CollectionForm collection={collection} pages={pages} onSubmit={onSubmit} onCancel={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Move Second up" }));
    await user.click(screen.getByRole("button", { name: "Update Collection" }));
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({ page_ids: ["p2", "p1"], time: { interval_seconds: 5400 } }),
      ),
    );
  });
});
