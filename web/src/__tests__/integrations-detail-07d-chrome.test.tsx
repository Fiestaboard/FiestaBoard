/**
 * BB-FC-9 (chrome): the desktop detail pane's title carries a mono status
 * badge, as in 07d `324:40267` (setup required `324:44888`), in place of the
 * enable switch, the "…" and the version chips, and the pane has no tab
 * strip. Nothing is lost: the version, the switch, README, Variables and the
 * per-plugin actions are in the section header's "Integration options".
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

const toggles: string[] = [];

beforeEach(() => {
  toggles.length = 0;
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
    http.patch("/api/v1/plugins/:id", async ({ params, request }) => {
      const body = (await request.json()) as { enabled?: boolean };
      toggles.push(`${body.enabled ? "enable" : "disable"} ${params.id}`);
      return HttpResponse.json(detail(String(params.id), String(params.id)));
    }),
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

describe("Integration detail pane chrome against 07d (BB-FC-9)", () => {
  it("titles the pane with the plugin name and a mono Configured badge", async () => {
    const pane = await openPane(userEvent.setup(), "Countdown");
    const heading = within(pane).getByRole("heading", { name: "Countdown", level: 2 });
    const badge = within(heading.parentElement!).getByText("Configured");
    expect(badge.closest("[data-slot=badge]")).toHaveClass("font-mono");
  });

  it("badges a plugin that still needs setup as Setup Required", async () => {
    const pane = await openPane(userEvent.setup(), "Weather");
    const heading = within(pane).getByRole("heading", { name: "Weather", level: 2 });
    const badge = within(heading.parentElement!).getByText("Setup Required");
    expect(badge.closest("[data-slot=badge]")).toHaveClass("font-mono");
  });

  it("drops the tab strip, the switch, the ⋯ and the version chips from the pane", async () => {
    const pane = await openPane(userEvent.setup(), "Countdown");
    expect(within(pane).queryByRole("tablist")).toBeNull();
    expect(within(pane).queryByRole("tabpanel")).toBeNull();
    expect(within(pane).queryByRole("switch", { name: /countdown/i })).toBeNull();
    expect(within(pane).queryByRole("button", { name: "More options" })).toBeNull();
    expect(within(pane).queryByText("v1.3.1")).toBeNull();
  });

  it("moves the version, the enable switch and README into the header's Integration options", async () => {
    const user = userEvent.setup();
    await openPane(user, "Countdown");
    const header = document.querySelector<HTMLElement>("[data-slot=page-header]")!;
    await user.click(within(header).getByRole("button", { name: "Integration options" }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByText("Countdown · v1.3.1 · Core")).toBeInTheDocument();
    expect(within(menu).getByRole("menuitem", { name: "README" })).toBeInTheDocument();
    expect(within(menu).getByRole("menuitem", { name: "Variables and live values" })).toBeInTheDocument();
    expect(within(menu).getByRole("menuitem", { name: /check for updates/i })).toBeInTheDocument();
    const enabled = within(menu).getByRole("menuitemcheckbox", { name: "Enabled" });
    expect(enabled).toHaveAttribute("aria-checked", "true");
    await user.click(enabled);
    await waitFor(() => expect(toggles).toEqual(["disable countdown"]));
  });

  it("drops the pane's items from the header menu once the pane goes (Marketplace tab)", async () => {
    const user = userEvent.setup();
    await openPane(user, "Countdown");
    await user.click(screen.getByRole("tab", { name: "Marketplace" }));
    const header = document.querySelector<HTMLElement>("[data-slot=page-header]")!;
    await user.click(within(header).getByRole("button", { name: "Integration options" }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByRole("menuitem", { name: /check for updates/i })).toBeInTheDocument();
    expect(within(menu).queryByRole("menuitem", { name: "README" })).toBeNull();
    expect(within(menu).queryByText("Countdown · v1.3.1 · Core")).toBeNull();
  });

  it("names the Enabled item's group after the integration", async () => {
    const user = userEvent.setup();
    await openPane(user, "Countdown");
    const header = document.querySelector<HTMLElement>("[data-slot=page-header]")!;
    await user.click(within(header).getByRole("button", { name: "Integration options" }));
    const group = await screen.findByRole("group", { name: "Countdown · v1.3.1 · Core" });
    expect(within(group).getByRole("menuitemcheckbox", { name: "Enabled" })).toBeInTheDocument();
  });

  it("keeps the header menu on a short landscape screen, where the pane still opens", async () => {
    // 844×390: wide enough for the pane (768+), short enough to count as
    // below the rail (BB-A-13), which hides the header's actions.
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query.startsWith("(min-width: 768") || query.includes("max-height") || query.includes("1023.98"),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    const user = userEvent.setup();
    await openPane(user, "Countdown");
    const header = document.querySelector<HTMLElement>("[data-slot=page-header]")!;
    await user.click(await within(header).findByRole("button", { name: "Integration options" }));
    expect(await screen.findByRole("menuitemcheckbox", { name: "Enabled" })).toBeInTheDocument();
  });
});
