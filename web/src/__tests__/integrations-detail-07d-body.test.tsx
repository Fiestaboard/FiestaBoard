/**
 * BB-FC-9 (body): the integration detail follows 07d `324:40267`: sections
 * under mono labels, "Unlocks N variables" chips and an outline "Use in a
 * page…", which takes over the old Demo Page box's Create Demo Page.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IntegrationsSection } from "../../app/routes/integrations";
import IntegrationsPage from "../../app/routes/integrations._index";
import { server } from "./mocks/server";

const plugin = (id: string, name: string, configured = true) => ({
  id,
  name,
  category: "utility",
  version: "1.3.1",
  description: `${name} description`,
  author: "FiestaBoard",
  enabled: true,
  configured,
  icon: "puzzle",
  config: {},
  source: { source_type: "builtin" },
  plugin_type: "data",
  update_available: false,
  instance_label: null,
  base_plugin_id: id,
});

const detail = (id: string, name: string) => ({
  ...plugin(id, name),
  config: { event_name: "Launch" },
  settings_schema: {
    type: "object",
    properties: {
      enabled: { type: "boolean", title: "Enable", default: true },
      event_name: { type: "string", title: "Event Name" },
    },
  },
  variables: { simple: { days: { description: "Days left" }, label: { description: "Event name" } } },
  max_lengths: {},
  env_vars: [],
  documentation: "README.md",
  has_demo: true,
  demo_page_id: null,
  instances: [],
});

beforeEach(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.startsWith("(min-width: 768"),
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
  server.use(
    http.get("/api/plugins", () =>
      HttpResponse.json({
        plugins: [plugin("countdown", "Countdown"), plugin("weather", "Weather", false)],
        total: 2,
        enabled_count: 2,
        plugin_system_enabled: true,
      }),
    ),
    http.get("/api/plugins/registry", () => HttpResponse.json({ entries: [] })),
    http.get("/api/oauth/connections", () => HttpResponse.json({ connections: [], redirect_uri: "" })),
    http.get("/api/settings/plugins", () => HttpResponse.json({ auto_update: false })),
    http.get("/api/v1/plugins/countdown", () => HttpResponse.json(detail("countdown", "Countdown"))),
    http.get("/api/v1/plugins/weather", () => HttpResponse.json(detail("weather", "Weather"))),
    http.get("/api/v1/plugins/:id/data", () => HttpResponse.json({ available: true, data: {} })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderSection() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <IntegrationsSection>
        <IntegrationsPage />
      </IntegrationsSection>
    </QueryClientProvider>,
  );
}

async function openPane(user: ReturnType<typeof userEvent.setup>, name: string) {
  renderSection();
  const row = await waitFor(() => {
    const found = [...document.querySelectorAll<HTMLButtonElement>("button[data-slot=list-row]")].find((el) =>
      el.textContent?.includes(name),
    );
    expect(found).toBeDefined();
    return found!;
  });
  await user.click(row);
  const pane = await screen.findByRole("complementary", { name: "Integration settings" });
  await within(pane).findByLabelText("Event Name");
  return pane;
}

describe("Integration detail body against 07d (BB-FC-9)", () => {
  it("labels the settings and the variables with mono section labels", async () => {
    const pane = await openPane(userEvent.setup(), "Countdown");
    for (const name of ["Settings", "Unlocks 2 variables"]) {
      const label = within(pane).getByRole("heading", { name, level: 3 });
      expect(label).toHaveClass("font-mono", "uppercase");
    }
  });

  it("lists each variable the plugin unlocks as a chip", async () => {
    const pane = await openPane(userEvent.setup(), "Countdown");
    const chips = within(pane).getByRole("list", { name: "Unlocks 2 variables" });
    expect(
      within(chips)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual(["countdown.days", "countdown.label"]);
  });

  it("offers Create Demo Page and a new page behind the outline Use in a page… button", async () => {
    const user = userEvent.setup();
    let created = 0;
    server.use(
      http.post("/api/plugins/countdown/demo-page", () => {
        created += 1;
        return HttpResponse.json({ page_id: "p1", recreated: false });
      }),
    );
    const pane = await openPane(user, "Countdown");
    const button = within(pane).getByRole("button", { name: "Use in a page…" });
    expect(button).toHaveAttribute("data-variant", "outline");
    await user.click(button);
    expect(await screen.findByRole("menuitem", { name: "New page" })).toBeInTheDocument();
    await user.click(screen.getByRole("menuitem", { name: "Create Demo Page" }));
    await waitFor(() => expect(created).toBe(1));
  });

  it("draws no Settings label when a ui:sections group names every field", async () => {
    server.use(
      http.get("/api/v1/plugins/countdown", () => {
        const base = detail("countdown", "Countdown");
        return HttpResponse.json({
          ...base,
          settings_schema: {
            ...base.settings_schema,
            "ui:sections": [{ id: "event", title: "Event", fields: ["event_name"] }],
          },
        });
      }),
    );
    const pane = await openPane(userEvent.setup(), "Countdown");
    expect(within(pane).getByRole("group", { name: "Event" })).toBeInTheDocument();
    expect(within(pane).queryByRole("heading", { name: "Settings", level: 3 })).toBeNull();
  });

  it("says why Create Demo Page is unavailable on the disabled item", async () => {
    server.use(
      http.get("/api/v1/plugins/countdown", () => {
        const base = detail("countdown", "Countdown");
        return HttpResponse.json({ ...base, settings_schema: { ...base.settings_schema, required: ["target_date"] } });
      }),
    );
    const user = userEvent.setup();
    const pane = await openPane(user, "Countdown");
    await user.click(within(pane).getByRole("button", { name: "Use in a page…" }));
    const item = await screen.findByRole("menuitem", { name: "Create Demo Page" });
    expect(item).toHaveAttribute("aria-disabled", "true");
    expect(item).toHaveAccessibleDescription(/configure the required settings/i);
  });

  it("offers no Use in a page… for an output or a transition, which put nothing on a page", async () => {
    server.use(
      http.get("/api/plugins", () =>
        HttpResponse.json({
          plugins: [{ ...plugin("countdown", "Countdown"), plugin_type: "transition" }],
          total: 1,
          enabled_count: 1,
          plugin_system_enabled: true,
        }),
      ),
    );
    const pane = await openPane(userEvent.setup(), "Countdown");
    expect(within(pane).queryByRole("button", { name: "Use in a page…" })).toBeNull();
  });
});
