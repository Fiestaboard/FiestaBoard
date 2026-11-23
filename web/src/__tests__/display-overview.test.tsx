import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { DisplayOverview } from "@/components/displays/display-overview";
import type { BoardInstance } from "@/lib/api";

import { server } from "./mocks/server";

const kitchen = { id: "kitchen", name: "Kitchen", device_type: "flagship", enabled: true } as BoardInstance;
const inAnHour = () => new Date(Date.now() + 3600000).toISOString();

function draw(detail: Record<string, unknown>) {
  server.use(
    http.get("/api/v1/boards/kitchen", () =>
      HttpResponse.json({ id: "kitchen", name: "Kitchen", source: "none", resolved_page_id: null, ...detail }),
    ),
    http.get("/api/v1/pages", () =>
      HttpResponse.json({
        pages: [
          { id: "pizza", name: "Pizza Special" },
          { id: "clock", name: "Clock & Date" },
        ],
        total: 2,
      }),
    ),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DisplayOverview board={kitchen} onPlayback={() => {}} onDiagnostics={() => {}} />
    </QueryClientProvider>,
  );
}

// BB-A-8: the Overview must agree with Home while an override runs.
describe("DisplayOverview while an override runs", () => {
  it("names the override's page, and when the Schedule takes back over", async () => {
    draw({
      override_page_id: "pizza",
      override_started_at: new Date().toISOString(),
      override_expires_at: inAnHour(),
      next_change_at: inAnHour(),
      next_change_reason: "override_ends",
      next_page_id: null,
    });
    expect(await screen.findByText(/Pizza Special/)).toBeInTheDocument();
    expect(screen.queryByText(/· None/)).not.toBeInTheDocument();
    expect(await screen.findByText(/then Schedule$/)).toBeInTheDocument();
    expect(screen.queryByText("No upcoming change reported")).not.toBeInTheDocument();
  });

  it("calls a composed override a composed message", async () => {
    draw({
      override_page_id: null,
      override_started_at: new Date().toISOString(),
      override_expires_at: inAnHour(),
      next_change_at: inAnHour(),
      next_change_reason: "override_ends",
      next_page_id: "clock",
    });
    expect(await screen.findByText(/Composed message/)).toBeInTheDocument();
    expect(await screen.findByText(/then Clock & Date/)).toBeInTheDocument();
  });

  it("still reports a change it cannot name a page for", async () => {
    draw({ next_change_at: inAnHour(), next_change_reason: "silence_starts", next_page_id: null });
    expect(await screen.findByText(/^Changes at /)).toBeInTheDocument();
  });
});

describe("DisplayOverview rows (FK-9)", () => {
  it("ends the Silence and Diagnostics rows in the kit's ListRow chevron", async () => {
    draw({});
    for (const name of [/Silence/, /Diagnostics/]) {
      const row = await screen.findByRole("button", { name });
      expect(row.querySelector('[data-slot="list-row-chevron"]')).not.toBeNull();
    }
  });
});
