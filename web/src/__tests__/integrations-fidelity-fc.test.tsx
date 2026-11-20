/**
 * BB-FC-8: Integrations list against 07d.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IntegrationsSection } from "../../app/routes/integrations";
import IntegrationsPage from "../../app/routes/integrations._index";
import { server } from "./mocks/server";

const plugin = (id: string, configured = true, enabled = true) => ({
  id,
  name: id,
  category: "utility",
  version: "1.0.0",
  description: `${id} description`,
  author: "FiestaBoard",
  enabled,
  configured,
  icon: "puzzle",
  config: {},
  source: { source_type: "builtin" },
  plugin_type: "data",
  update_available: false,
  instance_label: null,
  base_plugin_id: id,
});

function desktopViewport() {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.startsWith("(min-width: 768"),
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <IntegrationsSection>
        <IntegrationsPage />
      </IntegrationsSection>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  desktopViewport();
  server.use(
    http.get("/api/plugins", () =>
      HttpResponse.json({
        plugins: [plugin("Weather"), plugin("Transit", false), plugin("Music", true, false)],
        total: 3,
        enabled_count: 2,
        plugin_system_enabled: true,
      }),
    ),
    http.get("/api/plugins/registry", () => HttpResponse.json({ entries: [] })),
    http.get("/api/oauth/connections", () => HttpResponse.json({ connections: [], redirect_uri: "" })),
    http.get("/api/settings/plugins", () => HttpResponse.json({ auto_update: false })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const classes = (el: Element | null): string[] => (el?.getAttribute("class") ?? "").split(/\s+/);

/*
 * BB-FC-8: the Integrations list against 07d `324:40267` / `324:50158`: a
 * plain page (no card), a "…" header action, "Installed · n | Marketplace",
 * a 280px search on the right, and inset rows led by a status dot, with no
 * dividers.
 */
describe("Integrations list at the desktop (BB-FC-8)", () => {
  it("sits on the page, not in a card", async () => {
    renderList();
    await screen.findByRole("list", { name: "Installed" });
    const card = document.querySelector("[data-slot=page-card]");
    expect(card?.getAttribute("data-surface")).toBe("plain");
    // ...so its header and list sit on the page gutter, not a card's inset.
    expect(classes(card)).toContain("[&_[data-slot=page-header]]:px-0");
    // The plugin page's crumb and h2 (PageSubheader) lose the card's rule and
    // inset too, so they stay on the h1's gutter (07d `328:30630`).
    expect(classes(card)).toContain("[&_[data-slot=page-subheader]_.border-t]:px-0");
    expect(classes(card)).toContain("[&_[data-slot=page-subheader]_.border-t]:border-t-0");
  });

  it("puts Check for updates behind the header's More options button", async () => {
    const user = userEvent.setup();
    renderList();
    const header = document.querySelector<HTMLElement>("[data-slot=page-header]")!;
    expect(within(header).queryByRole("button", { name: /check for updates/i })).toBeNull();
    let checked = 0;
    server.use(
      http.post("/api/plugins/updates/check", () => {
        checked += 1;
        return HttpResponse.json({ updates_available: [] });
      }),
    );
    await user.click(within(header).getByRole("button", { name: "More options" }));
    await user.click(await screen.findByRole("menuitem", { name: /check for updates/i }));
    await waitFor(() => expect(checked).toBe(1));
  });

  it("reads the tabs as Installed · n | Marketplace, without count badges", async () => {
    renderList();
    expect(await screen.findByRole("tab", { name: "Installed · 3" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Marketplace" })).toBeInTheDocument();
  });

  it("draws a 280px search at the right of the tabs", async () => {
    renderList();
    const search = await screen.findByRole("textbox", { name: "Search installed plugins..." });
    const box = search.parentElement!;
    expect(classes(box)).toContain("sm:w-70");
    expect(classes(box)).toContain("sm:justify-self-end");
  });

  it("insets rows with no dividers, led by a status dot, title semibold", async () => {
    renderList();
    const installed = await screen.findByRole("list", { name: "Installed" });
    expect(classes(installed)).not.toContain("divide-y");
    expect(classes(installed)).toContain("p-1");
    const row = await within(installed).findByRole("button", { name: /^Weather/ });
    expect(row.querySelector("[data-slot=status-dot]")).not.toBeNull();
    expect(row.querySelector("[data-slot=icon-tile]")).toBeNull();
    expect(row.getAttribute("data-size")).toBe("default");
    expect(
      row.querySelector("[data-slot=list-row-title] [data-weight=semibold], [data-slot=list-row-title] .font-semibold"),
    ).not.toBeNull();
    // Group labels are flush with the list (x 289 = the card's edge).
    const label = screen.getByRole("heading", { level: 2, name: "Installed" });
    expect(classes(label)).not.toContain("px-4");
  });
});
