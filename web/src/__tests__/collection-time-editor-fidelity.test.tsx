import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { CollectionPreview } from "@/components/collection-preview";
import type { Collection, CollectionEvaluation, Page } from "@/lib/api";
import { api } from "@/lib/api";

import { CollectionForm } from "../../app/routes/collections";
import { server } from "./mocks/server";

// BB-FP-22: time-based Collection editor details (Figma 312:74870).

const pages = [
  { id: "p1", name: "Morning commute", device_type: "flagship" },
  { id: "p2", name: "Market open", device_type: "flagship" },
] as Page[];

const evaluation = {
  collection_id: "collection:c1",
  selection_mode: "time",
  page_id: "p1",
  at: "2026-01-01T07:02:00",
  rules: null,
  matched_rule: null,
  timeline: [
    { from: "2026-01-01T07:02:00", until: "2026-01-01T07:15:00", page_id: "p1" },
    { from: "2026-01-01T07:15:00", until: "2026-01-01T07:25:00", page_id: "p2" },
    { from: "2026-01-01T07:25:00", until: "2026-01-01T07:35:00", page_id: "p1" },
  ],
} as CollectionEvaluation;

function preview(props: Partial<React.ComponentProps<typeof CollectionPreview>> = {}) {
  server.use(http.post("/api/pages/p1/preview", () => HttpResponse.json({ message: "HELLO" })));
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
        intervalSeconds={600}
        schedule="Weekdays 6:00 AM–9:00 AM"
        {...props}
      />
    </QueryClientProvider>,
  );
}

describe("Now in this Collection (BB-FP-22)", () => {
  it("asks the dry run for a timeline window, which it otherwise leaves empty", async () => {
    let body: unknown;
    server.use(
      http.post("/api/collections/collection:c1/dry-run", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(evaluation);
      }),
    );
    await api.evaluateCollection("collection:c1", undefined, 1200);
    expect(body).toEqual({ window_seconds: 1200 });
  });

  it("says how long the page shows, from the dry-run timeline", () => {
    preview();
    expect(screen.getByText(/^Morning commute · showing until 7:15\sAM$/)).toBeInTheDocument();
  });

  it("names the next page with its duration and when the Schedule runs the Collection", () => {
    preview();
    expect(
      screen.getByText("Next: Market open (10 min) · Collection runs Weekdays 6:00 AM–9:00 AM in the Schedule"),
    ).toBeInTheDocument();
  });

  it("formats the evaluation time instead of printing a raw locale timestamp", () => {
    preview();
    const line = screen.getByText(/Saved Collection · cached data/);
    expect(line.textContent).not.toMatch(/\d+\/\d+\/\d{4}/);
  });

  it("does not claim an end when the timeline has a single window", () => {
    preview({ evaluation: { ...evaluation, timeline: [evaluation.timeline![0]] } });
    expect(screen.queryByText(/showing until/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Next:/)).not.toBeInTheDocument();
    expect(screen.getByText("Selected: Morning commute")).toBeInTheDocument();
  });
});

describe("Lifted page row (BB-FP-22)", () => {
  it("keeps the card surface while lifted instead of turning muted", async () => {
    const user = userEvent.setup();
    const collection = {
      id: "collection:c1",
      name: "Weekday mornings",
      page_ids: ["p1", "p2"],
      selection_mode: "time",
      time: { interval_seconds: 600 },
      variable: null,
      random: null,
      created_at: "2026-01-01",
    } as Collection;
    render(<CollectionForm collection={collection} pages={pages} onSubmit={vi.fn()} onCancel={vi.fn()} />);
    const row = screen.getAllByRole("listitem").find((item) => item.textContent?.includes("Morning commute"))!;
    row.focus();
    await user.keyboard(" ");
    const lifted = document.querySelector<HTMLElement>("[data-lifted]")!;
    expect(lifted).not.toBeNull();
    const surface = lifted.querySelector<HTMLElement>('[data-slot="list-row"]')!;
    // The kit tints a lifted row's surface from an ancestor (in-data-[lifted]).
    expect(surface.className).toMatch(/in-data-\[lifted\]:bg-card/);
    expect(surface.className).not.toMatch(/in-data-\[lifted\]:bg-accent/);
  });
});
