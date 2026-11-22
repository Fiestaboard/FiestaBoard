import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Collection, Page, ScheduleEntry } from "@/lib/api";

import CollectionsPage from "../../app/routes/collections._index";
import { server } from "./mocks/server";

// BB-FP-20: collection cards follow Figma 342:187593.

vi.mock("@/hooks/use-view-transition", () => ({ useViewTransition: () => ({ push: vi.fn() }) }));

const pages = Array.from({ length: 4 }, (_, i) => ({
  id: `p${i}`,
  name: `Page ${i}`,
  device_type: "flagship",
})) as Page[];

const base = { variable: null, random: null, created_at: "2026-01-01", time: { interval_seconds: 600 } };
const collections = [
  {
    ...base,
    id: "collection:mornings",
    name: "Weekday mornings",
    page_ids: ["p0", "p1", "p2", "p3"],
    selection_mode: "time",
  },
  {
    ...base,
    id: "collection:weather",
    name: "Weather-aware morning",
    page_ids: ["p0", "p1"],
    selection_mode: "variable",
    variable: {
      rules: [
        { expression: "1 = 1", page_id: "p0" },
        { expression: "2 = 2", page_id: "p1" },
      ],
      default_page_id: "p0",
      poll_seconds: 10,
    },
  },
  {
    ...base,
    id: "collection:mix",
    name: "Weekend mix",
    page_ids: ["p0", "p1", "p2"],
    selection_mode: "random",
    random: { interval_seconds: 900 },
  },
] as Collection[];

const schedules = [
  {
    id: "s1",
    page_id: "collection:mornings",
    start_time: "06:00",
    end_time: "09:00",
    day_pattern: "weekdays",
    enabled: true,
    created_at: "2026-01-01",
  },
] as ScheduleEntry[];

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

async function card(name: string) {
  const title = await screen.findByText(name);
  return title.closest<HTMLElement>("[data-slot=card]")!;
}

describe("Collection cards (BB-FP-20)", () => {
  beforeEach(() => {
    localStorage.clear();
    server.use(
      http.get("/api/v1/collections", () => HttpResponse.json({ collections })),
      http.get("/api/v1/pages", () => HttpResponse.json({ pages })),
      http.get("/api/v1/schedules", () => HttpResponse.json({ schedules, total: 1 })),
      http.post("/api/pages/preview/batch", () => HttpResponse.json({ previews: {} })),
    );
  });

  it("puts an outline mode chip right after the title, with no Beta chip", async () => {
    renderLibrary();
    const weather = await card("Weather-aware morning");
    const chip = within(weather).getByText("Variable / expression");
    expect(chip).toHaveAttribute("data-slot", "badge");
    expect(chip.className).not.toMatch(/bg-secondary/);
    expect(within(weather).getByText("Weather-aware morning").nextElementSibling).toBe(chip);
    expect(within(weather).queryByText("Beta")).not.toBeInTheDocument();
  });

  it("writes the per-mode meta line", async () => {
    renderLibrary();
    expect(within(await card("Weekday mornings")).getByText("4 pages · 40 min · repeats")).toBeInTheDocument();
    expect(within(await card("Weather-aware morning")).getByText("2 rules + default")).toBeInTheDocument();
    expect(within(await card("Weekend mix")).getByText("3 pages · every 15 min")).toBeInTheDocument();
  });

  it("says when the Schedule runs a collection, or that it is not scheduled", async () => {
    renderLibrary();
    expect(
      await within(await card("Weekday mornings")).findByText(/^Schedule · Weekdays 6:00\sAM–9:00\sAM$/),
    ).toBeInTheDocument();
    expect(within(await card("Weekend mix")).getByText("Not scheduled")).toBeInTheDocument();
  });

  it("shows one full-bleed board at the top of the card instead of a stacked inset", async () => {
    renderLibrary();
    const mornings = await card("Weekday mornings");
    const cover = within(mornings).getByTestId("collection-page-stack");
    expect(mornings.firstElementChild).toBe(cover);
    await waitFor(() => expect(cover.querySelectorAll("[data-slot=collection-cover-board]")).toHaveLength(1));
  });
});
