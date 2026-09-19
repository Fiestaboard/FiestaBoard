/**
 * The config sheet's Template Variables table reads live values from
 * `GET /v1/plugins/{id}/data`, not from the deprecated
 * `GET /displays/{type}/raw` (#1911).
 *
 * The two routes answer the same fetch, so a page still on the old one renders
 * identically until the old one is removed on its Sunset date — which is why
 * this test spies on the legacy path as well as asserting the new one: a
 * value in the cell proves the page read *something*, and only the zero on the
 * legacy counter proves it was the successor.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import IntegrationsPage from "../../app/routes/integrations._index";
import { server } from "./mocks/server";

const API_BASE = "/api";
const PLUGIN_ID = "date_time";

function mockDateTime() {
  let legacyRawReads = 0;
  let v1DataReads = 0;

  const detail = {
    id: PLUGIN_ID,
    name: "Date & Time",
    version: "1.0.0",
    description: "Date and time",
    author: "FiestaBoard",
    icon: "clock",
    category: "utility",
    plugin_type: "data",
    enabled: true,
    config: {},
    settings_schema: { type: "object", properties: {} },
    variables: { simple: { time: { description: "Current time" } } },
    max_lengths: { time: 5 },
    env_vars: [],
    documentation: null,
    has_demo: false,
    demo_page_id: null,
    instance_label: null,
    base_plugin_id: PLUGIN_ID,
    instances: [],
  };

  server.use(
    http.get(`${API_BASE}/plugins`, () =>
      HttpResponse.json({
        plugins: [
          {
            id: PLUGIN_ID,
            name: "Date & Time",
            category: "utility",
            version: "1.0.0",
            description: "Date and time",
            author: "FiestaBoard",
            enabled: true,
            configured: true,
            icon: "clock",
            config: {},
            source: { source_type: "builtin" as const },
            update_available: false,
            instance_label: null,
            base_plugin_id: PLUGIN_ID,
          },
        ],
        plugin_system_enabled: true,
        total: 1,
        enabled_count: 1,
      }),
    ),
    http.get(`${API_BASE}/plugins/registry`, () => HttpResponse.json({ entries: [] })),
    http.get(`${API_BASE}/v1/plugins/${PLUGIN_ID}`, () => HttpResponse.json(detail)),

    // The successor: what the sheet must read.
    http.get(`${API_BASE}/v1/plugins/${PLUGIN_ID}/data`, () => {
      v1DataReads += 1;
      return HttpResponse.json({
        plugin_id: PLUGIN_ID,
        available: true,
        data: { time: "12:34" },
        lines: ["12:34"],
        text: "12:34",
        error: null,
      });
    }),

    // The deprecated route, answering the same payload in its old shape so a
    // page still calling it renders a value too. Only the counter tells.
    http.get(`${API_BASE}/displays/${PLUGIN_ID}/raw`, () => {
      legacyRawReads += 1;
      return HttpResponse.json({
        display_type: PLUGIN_ID,
        data: { time: "12:34" },
        available: true,
        error: null,
      });
    }),
  );

  return { legacyRawReads: () => legacyRawReads, v1DataReads: () => v1DataReads };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 60_000, refetchOnMount: true },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <IntegrationsPage />
    </QueryClientProvider>,
  );
}

describe("Integrations — Template Variables live values", () => {
  it("reads live values from GET /v1/plugins/{id}/data and never from the deprecated raw route", async () => {
    const reads = mockDateTime();
    const user = userEvent.setup();
    renderPage();

    await user.click((await screen.findAllByRole("button", { name: /configure/i }))[0]);
    await screen.findByRole("heading", { name: /template variables/i });

    // The live value lands in the Current Value cell.
    await waitFor(() => expect(screen.getByText("12:34")).toBeInTheDocument());

    expect(reads.v1DataReads()).toBe(1);
    expect(reads.legacyRawReads()).toBe(0);
  });
});
