/**
 * Marketplace "Added" column (issue #1999).
 *
 * The list view can sort by Name, Category and Author, but nothing let a user
 * see what is new. Each registry entry now carries an `added` date, surfaced as
 * a sortable "Added" column that defaults to newest-first when selected. These
 * tests pin that the column renders the date and that clicking its header
 * orders the rows newest → oldest.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import IntegrationsPage from "../../app/routes/integrations._index";
import { server } from "./mocks/server";

const API_BASE = "/api";

interface MockRegistryEntry {
  id: string;
  name: string;
  category: string;
  added?: string;
}

/** Marketplace fixtures: nothing installed, `entries` available in the registry. */
function mockRegistry(entries: MockRegistryEntry[]) {
  const full = entries.map((e) => ({
    description: `${e.name} description`,
    repository: `https://example.com/${e.id}`,
    branch: "main",
    author: "FiestaBoard",
    fiestaboard_version: ">=8.0.0",
    icon: "puzzle",
    installed: false,
    teaser: "",
    previews: [],
    added: "",
    ...e,
  }));
  server.use(
    http.get(`${API_BASE}/plugins`, () =>
      HttpResponse.json({ plugins: [], plugin_system_enabled: true, total: 0, enabled_count: 0 }),
    ),
    http.get(`${API_BASE}/plugins/registry`, () => HttpResponse.json({ entries: full })),
  );
}

async function openMarketplaceList() {
  const user = userEvent.setup();
  await user.click(await screen.findByRole("tab", { name: /marketplace/i }));
  await user.click(await screen.findByRole("button", { name: /list view/i }));
  return user;
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

/** Names of the marketplace rows, in the order they appear in the table body. */
function rowNamesInOrder(names: string[]): string[] {
  return screen
    .getAllByRole("row")
    .map((row) => names.find((n) => row.textContent?.includes(n)))
    .filter((n): n is string => Boolean(n));
}

describe("Marketplace — Added column", () => {
  it("shows each entry's added date in the list view", async () => {
    mockRegistry([{ id: "weather", name: "Weather", category: "weather", added: "2026-05-02" }]);
    renderPage();
    await openMarketplaceList();

    const cell = await screen.findByText("Weather");
    const row = cell.closest("tr")!;
    expect(row.textContent).toContain("2026-05-02");
  });

  it("sorts newest-first when the Added header is clicked", async () => {
    mockRegistry([
      { id: "oldest", name: "Oldest", category: "utility", added: "2026-01-01" },
      { id: "newest", name: "Newest", category: "utility", added: "2026-05-01" },
      { id: "middle", name: "Middle", category: "utility", added: "2026-03-01" },
    ]);
    renderPage();
    const user = await openMarketplaceList();

    await user.click(await screen.findByRole("columnheader", { name: /added/i }));

    expect(rowNamesInOrder(["Oldest", "Newest", "Middle"])).toEqual(["Newest", "Middle", "Oldest"]);
  });

  it("toggles to oldest-first on a second click of the Added header", async () => {
    mockRegistry([
      { id: "oldest", name: "Oldest", category: "utility", added: "2026-01-01" },
      { id: "newest", name: "Newest", category: "utility", added: "2026-05-01" },
      { id: "middle", name: "Middle", category: "utility", added: "2026-03-01" },
    ]);
    renderPage();
    const user = await openMarketplaceList();

    const header = await screen.findByRole("columnheader", { name: /added/i });
    await user.click(header);
    await user.click(header);

    expect(rowNamesInOrder(["Oldest", "Newest", "Middle"])).toEqual(["Oldest", "Middle", "Newest"]);
  });

  it("sorts entries with no added date last under newest-first", async () => {
    mockRegistry([
      { id: "dated", name: "Dated", category: "utility", added: "2026-01-01" },
      { id: "undated", name: "Undated", category: "utility", added: "" },
    ]);
    renderPage();
    const user = await openMarketplaceList();

    await user.click(await screen.findByRole("columnheader", { name: /added/i }));

    expect(rowNamesInOrder(["Dated", "Undated"])).toEqual(["Dated", "Undated"]);
  });
});
