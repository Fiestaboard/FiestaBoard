/**
 * The config sheet's Template Variables table: each variable's token is a copy
 * control that writes the full `{{plugin.var}}` template token, not the
 * shortened `plugin.var` it displays.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import IntegrationsPage from "../../app/routes/integrations._index";
import { server } from "./mocks/server";

const API_BASE = "/api";
const PLUGIN_ID = "date_time";

function mockDateTime() {
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

    http.get(`${API_BASE}/v1/plugins/${PLUGIN_ID}/data`, () =>
      HttpResponse.json({
        plugin_id: PLUGIN_ID,
        available: true,
        data: { time: "12:34" },
        lines: ["12:34"],
        text: "12:34",
        error: null,
      }),
    ),
  );
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

describe("Integrations — Template Variables copy", () => {
  it("copies the full template token when a variable's token is clicked", async () => {
    mockDateTime();
    const user = userEvent.setup();
    renderPage();

    await user.click((await screen.findAllByRole("button", { name: /configure/i }))[0]);
    await user.click(await screen.findByRole("button", { name: /copy date_time\.time/i }));

    await expect(navigator.clipboard.readText()).resolves.toBe("{{date_time.time}}");
  });
});
