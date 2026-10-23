/**
 * Sortable table headers on the Integrations page are keyboard operable and
 * announce their sort state (issue #2003).
 *
 * Both tables used to put `onClick` on a bare `<th>`: no focus stop, no key
 * handling, and the direction lived only in a chevron icon. axe does not flag
 * that, so these tests drive the headers the way a keyboard / screen reader
 * user would: by role, by Tab, and by Enter / Space, and read `aria-sort`.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import IntegrationsPage from "../../app/routes/integrations._index";
import { server } from "./mocks/server";

const API_BASE = "/api";

function installed(id: string, name: string, category: string) {
  return {
    id,
    name,
    category,
    version: "1.0.0",
    description: `${name} description`,
    author: "FiestaBoard",
    enabled: true,
    configured: true,
    icon: "puzzle",
    config: {},
    source: { source_type: "builtin" as const },
    update_available: false,
    instance_label: null,
    base_plugin_id: id,
  };
}

function registryEntry(id: string, name: string) {
  return {
    id,
    name,
    description: `${name} description`,
    repository: `https://example.com/${id}`,
    branch: "main",
    author: "FiestaBoard",
    fiestaboard_version: ">=8.0.0",
    icon: "puzzle",
    category: "utility",
    installed: false,
    teaser: "",
    previews: [],
  };
}

function mockApi() {
  const plugins = [installed("bravo", "Bravo", "utility"), installed("alpha", "Alpha", "weather")];
  server.use(
    http.get(`${API_BASE}/plugins`, () =>
      HttpResponse.json({ plugins, plugin_system_enabled: true, total: 2, enabled_count: 2 }),
    ),
    http.get(`${API_BASE}/plugins/registry`, () =>
      HttpResponse.json({ entries: [registryEntry("zulu", "Zulu"), registryEntry("yankee", "Yankee")] }),
    ),
  );
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <IntegrationsPage />
    </QueryClientProvider>,
  );
}

function headerCell(name: RegExp) {
  return screen.getByRole("columnheader", { name });
}

function rowOrder(names: string[]): string[] {
  const seen: string[] = [];
  for (const row of screen.getAllByRole("row")) {
    for (const n of names) if (within(row).queryByText(n)) seen.push(n);
  }
  return seen;
}

describe("Installed table — sortable headers (#2003)", () => {
  it("exposes each sortable header as a button", async () => {
    mockApi();
    renderPage();
    await screen.findByText("Alpha");

    for (const name of [/^name/i, /^category/i, /^status/i]) {
      expect(within(headerCell(name)).getByRole("button")).toBeInTheDocument();
    }
  });

  it("marks the active column with aria-sort and the rest with none", async () => {
    mockApi();
    renderPage();
    await screen.findByText("Alpha");

    expect(headerCell(/^name/i)).toHaveAttribute("aria-sort", "ascending");
    expect(headerCell(/^category/i)).toHaveAttribute("aria-sort", "none");
  });

  it("sorts with Enter on a focused header, and updates aria-sort", async () => {
    mockApi();
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Alpha");

    const nameButton = within(headerCell(/^name/i)).getByRole("button");
    nameButton.focus();
    expect(nameButton).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(headerCell(/^name/i)).toHaveAttribute("aria-sort", "descending");
    expect(rowOrder(["Alpha", "Bravo"])).toEqual(["Bravo", "Alpha"]);
  });

  it("sorts with Space after tabbing to the next header", async () => {
    mockApi();
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Alpha");

    within(headerCell(/^name/i)).getByRole("button").focus();
    await user.tab();
    expect(within(headerCell(/^category/i)).getByRole("button")).toHaveFocus();
    await user.keyboard(" ");

    expect(headerCell(/^category/i)).toHaveAttribute("aria-sort", "ascending");
    expect(headerCell(/^name/i)).toHaveAttribute("aria-sort", "none");
    // utility < weather
    expect(rowOrder(["Alpha", "Bravo"])).toEqual(["Bravo", "Alpha"]);
  });
});

describe("Marketplace list — sortable headers (#2003)", () => {
  async function openList(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByRole("tab", { name: /marketplace/i }));
    await user.click(await screen.findByRole("button", { name: /list view/i }));
    await screen.findByText("Zulu");
  }

  it("exposes each sortable header as a button", async () => {
    mockApi();
    const user = userEvent.setup();
    renderPage();
    await openList(user);

    for (const name of [/^name/i, /^category/i, /^author/i, /^added/i]) {
      expect(within(headerCell(name)).getByRole("button")).toBeInTheDocument();
    }
  });

  it("starts with Name ascending and the other columns none", async () => {
    mockApi();
    const user = userEvent.setup();
    renderPage();
    await openList(user);

    expect(headerCell(/^name/i)).toHaveAttribute("aria-sort", "ascending");
    expect(headerCell(/^author/i)).toHaveAttribute("aria-sort", "none");
  });

  it("toggles direction with Enter and reflects it in aria-sort", async () => {
    mockApi();
    const user = userEvent.setup();
    renderPage();
    await openList(user);

    expect(rowOrder(["Yankee", "Zulu"])).toEqual(["Yankee", "Zulu"]);
    within(headerCell(/^name/i)).getByRole("button").focus();
    await user.keyboard("{Enter}");

    expect(headerCell(/^name/i)).toHaveAttribute("aria-sort", "descending");
    expect(rowOrder(["Yankee", "Zulu"])).toEqual(["Zulu", "Yankee"]);
  });
});
