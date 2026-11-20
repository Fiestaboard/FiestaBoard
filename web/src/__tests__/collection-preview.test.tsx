import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { CollectionPreview } from "@/components/collection-preview";
import type { CollectionEvaluation, Page } from "@/lib/api";
import { api } from "@/lib/api";

import { server } from "./mocks/server";

const evaluation = {
  collection_id: "collection:c1",
  selection_mode: "time",
  page_id: "p1",
  at: "2026-01-01T07:02:00Z",
  rules: [],
  matched_rule: null,
} as CollectionEvaluation;
const pages = [{ id: "p1", name: "Morning", device_type: "flagship" }] as Page[];
function view(props: Partial<React.ComponentProps<typeof CollectionPreview>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CollectionPreview
        evaluation={evaluation}
        pages={pages}
        mode="time"
        dirty={false}
        loading={false}
        failed={false}
        {...props}
      />
    </QueryClientProvider>,
  );
}
describe("saved Collection preview", () => {
  it("evaluates saved state using the read-only legacy endpoint", async () => {
    let body;
    server.use(
      http.post("/api/collections/collection:c1/dry-run", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(evaluation);
      }),
    );
    expect(await api.evaluateCollection("collection:c1")).toEqual(evaluation);
    expect(body).toEqual({});
  });
  it("hides saved results while draft edits are present", () => {
    view({ dirty: true });
    expect(screen.getByText("Save your changes to evaluate this Collection.")).toBeInTheDocument();
    expect(screen.queryByText("Selected: Morning")).not.toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
  it("does not guess a page on failure", () => {
    view({ failed: true, evaluation: undefined });
    expect(screen.getByText("Collection evaluation is unavailable.")).toBeInTheDocument();
    expect(screen.queryByText(/Selected:/)).not.toBeInTheDocument();
  });
  it("shows an empty state for a missing selection", () => {
    view({ evaluation: { ...evaluation, page_id: null } });
    expect(screen.getByText("No page was selected.")).toBeInTheDocument();
  });
  it("labels a result as saved cached data rather than physical display state", async () => {
    server.use(http.post("/api/pages/p1/preview", () => HttpResponse.json({ message: "HELLO" })));
    view();
    expect(screen.getByText("Selected: Morning")).toBeInTheDocument();
    expect(screen.getByText(/Saved Collection · cached data/)).toBeInTheDocument();
  });
  // BB-B-12: the board sits in a phone-hero viewport that fits the card
  // (settling a board that overflows a little), not a fixed-size board
  // centred in it and clipped on both sides.
  it("fits the evaluated board to the card in every mode", async () => {
    server.use(http.post("/api/pages/p1/preview", () => HttpResponse.json({ message: "GROCERIES" })));
    for (const mode of ["time", "variable", "random"] as const) {
      const { container, unmount } = view({ mode });
      const viewport = container.querySelector('[data-testid="collection-preview-board"] [data-layout]');
      expect(viewport).toHaveAttribute("data-layout", "phone-hero");
      expect(viewport).toHaveAttribute("data-mode", "fit");
      // From md the board box is the hero's 373px, so a Flagship needs no scroll chrome.
      expect(container.querySelector('[data-testid="collection-preview-board"]')).toHaveClass("md:w-[373px]");
      expect(container.querySelector('[data-testid="collection-preview-board"]')).not.toHaveClass("lg:w-auto");
      unmount();
    }
  });
});
