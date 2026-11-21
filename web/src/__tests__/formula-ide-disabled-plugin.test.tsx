/**
 * BB-E-12 (Figma 307:46094, H6): a page that reads an integration that is
 * switched off. Live shows ??? and now says why; Sample fills the
 * integration's example values from `GET /v1/variables` `disabled_plugins`.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useFormulaIde } from "@/components/formula-ide/use-formula-ide";
import type { RenderTarget } from "@/lib/api/formula-debug";

import { server } from "./mocks/server";

const TEMPLATE = ["{{date_time.day_of_week}}", "{{date_time.time}}", "{{weather.temp}}°"];
const target: RenderTarget = { template: TEMPLATE, deviceType: "flagship", boardId: "kitchen" };
const bodies: Array<Record<string, unknown>> = [];

beforeEach(() => {
  bodies.length = 0;
  server.use(
    http.get("/api/v1/variables", () =>
      HttpResponse.json({
        variables: { weather: ["temp"] },
        max_lengths: {},
        variable_metadata: { weather: { temp: { example: "70" } } },
        colors: {},
        symbols: [],
        filters: [],
        formatting: {},
        syntax_examples: {},
        disabled_plugins: {
          date_time: { name: "Date & Time", examples: { time: "7:00 AM", day_of_week: "MONDAY" } },
          spotify: { name: "Spotify", examples: { track: "SONG" } },
        },
      }),
    ),
    http.post("/api/templates/render", async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      bodies.push(body);
      return HttpResponse.json({
        rendered: "MONDAY\n7:00 AM\n70°",
        lines: [],
        line_count: 3,
        diagnostics: { formulas: [], lines: [] },
        sources: { weather: { state: "fresh", updated_at: null } },
      });
    }),
  );
});

function Harness() {
  const ide = useFormulaIde({
    target,
    available: true,
    live: { diagnostics: { formulas: [], lines: [] }, lines: ["???", "???", "72°"], failed: false },
    desktop: false,
    mirroring: false,
    stopMirroring: vi.fn(),
    boardCols: 22,
    editTemplateLine: vi.fn(),
  });
  return (
    <>
      {ide.bodyControls}
      {ide.previewFooter}
    </>
  );
}

function renderHarness() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>,
  );
}

describe("An integration that is switched off", () => {
  it("Live explains why it shows ??? and links to Integrations", async () => {
    renderHarness();
    const card = await screen.findByTestId("missing-values");
    expect(within(card).getByText("1 missing")).toBeInTheDocument();
    expect(card).toHaveTextContent("date_time.day_of_week — Date & Time is off in Integrations → line 1, 2 shows ???");
    expect(within(card).getByRole("link", { name: "Open Integrations" })).toBeInTheDocument();
    expect(card).not.toHaveTextContent("Spotify");
  });

  it("Sample fills in its example values", async () => {
    renderHarness();
    const group = await screen.findByRole("radiogroup", { name: "Preview data" });
    await userEvent.click(within(group).getByRole("radio", { name: "Sample" }));
    await waitFor(() =>
      expect(bodies.at(-1)).toMatchObject({
        preview: {
          values: { "weather.temp": "70", "date_time.time": "7:00 AM", "date_time.day_of_week": "MONDAY" },
        },
      }),
    );
    expect(screen.queryByText(/keep the hub's data|have no example/i)).toBeNull();
  });

  it("Missing names it as off, not as simulated", async () => {
    renderHarness();
    const group = await screen.findByRole("radiogroup", { name: "Preview data" });
    await userEvent.click(within(group).getByRole("radio", { name: "Missing" }));
    await waitFor(() => expect(bodies.at(-1)).toMatchObject({ preview: { missing: ["weather", "date_time"] } }));
    expect(await screen.findByTestId("missing-values")).toHaveTextContent("Date & Time is off in Integrations");
  });
});
