/**
 * Marketplace sorting by when a plugin was added (issue #1999).
 *
 * Requested on Discord: the list view could sort by Name, Category and Author,
 * so there was no way to see what is new in a catalogue that grew from 54 to 63
 * entries in a day.
 *
 * Dates arrive as ISO strings (`YYYY-MM-DD`), which compare correctly as
 * strings, so the interesting behaviour is the ordering rules around them:
 * first click is newest-first, ties fall back to name, and entries with no date
 * sort last in *both* directions rather than counting as the oldest.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import IntegrationsPage from "../../app/routes/integrations._index";
import { server } from "./mocks/server";

const API_BASE = "/api";

interface Entry {
  id: string;
  name: string;
  added?: string;
}

function mockRegistry(entries: Entry[]) {
  const full = entries.map((e) => ({
    description: `${e.name} description`,
    repository: `https://example.com/${e.id}`,
    branch: "main",
    author: "FiestaBoard",
    fiestaboard_version: ">=8.0.0",
    icon: "puzzle",
    category: "utility",
    installed: false,
    teaser: "",
    previews: [],
    ...e,
  }));
  server.use(
    http.get(`${API_BASE}/plugins`, () =>
      HttpResponse.json({ plugins: [], plugin_system_enabled: true, total: 0, enabled_count: 0 }),
    ),
    http.get(`${API_BASE}/plugins/registry`, () => HttpResponse.json({ entries: full })),
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

/** Open Marketplace → list view, where entries render as table rows. */
async function openMarketplaceList(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("tab", { name: /marketplace/i }));
  await user.click(await screen.findByRole("button", { name: /list view/i }));
}

/** Plugin names in the order the table currently renders them. */
function renderedOrder(names: string[]): string[] {
  const rows = screen.getAllByRole("row");
  const seen: string[] = [];
  for (const row of rows) {
    for (const name of names) {
      if (within(row).queryByText(name)) seen.push(name);
    }
  }
  return seen;
}

const NAMES = ["Alpha", "Bravo", "Charlie", "Delta"];

describe("Marketplace — sort by added date", () => {
  it("offers an Added column", async () => {
    mockRegistry([{ id: "alpha", name: "Alpha", added: "2026-03-22" }]);
    const user = userEvent.setup();
    renderPage();
    await openMarketplaceList(user);

    expect(screen.getByText("Added")).toBeInTheDocument();
  });

  it("renders the date on each row", async () => {
    mockRegistry([{ id: "alpha", name: "Alpha", added: "2026-03-22" }]);
    const user = userEvent.setup();
    renderPage();
    await openMarketplaceList(user);

    // Formatted for the viewer's locale, so match the year rather than a format.
    expect(screen.getByText(/2026/)).toBeInTheDocument();
  });

  it("sorts newest first on the first click", async () => {
    mockRegistry([
      { id: "alpha", name: "Alpha", added: "2026-03-22" },
      { id: "bravo", name: "Bravo", added: "2026-09-13" },
      { id: "charlie", name: "Charlie", added: "2026-05-02" },
    ]);
    const user = userEvent.setup();
    renderPage();
    await openMarketplaceList(user);

    await user.click(screen.getByText("Added"));

    expect(renderedOrder(NAMES)).toEqual(["Bravo", "Charlie", "Alpha"]);
  });

  it("reverses to oldest first on the second click", async () => {
    mockRegistry([
      { id: "alpha", name: "Alpha", added: "2026-03-22" },
      { id: "bravo", name: "Bravo", added: "2026-09-13" },
      { id: "charlie", name: "Charlie", added: "2026-05-02" },
    ]);
    const user = userEvent.setup();
    renderPage();
    await openMarketplaceList(user);

    await user.click(screen.getByText("Added"));
    await user.click(screen.getByText("Added"));

    expect(renderedOrder(NAMES)).toEqual(["Alpha", "Charlie", "Bravo"]);
  });

  it("orders same-day entries by name", async () => {
    mockRegistry([
      { id: "delta", name: "Delta", added: "2026-05-02" },
      { id: "bravo", name: "Bravo", added: "2026-05-02" },
      { id: "alpha", name: "Alpha", added: "2026-05-02" },
    ]);
    const user = userEvent.setup();
    renderPage();
    await openMarketplaceList(user);

    await user.click(screen.getByText("Added"));

    expect(renderedOrder(NAMES)).toEqual(["Alpha", "Bravo", "Delta"]);
  });

  it("sorts entries with no date last in both directions", async () => {
    mockRegistry([
      { id: "alpha", name: "Alpha" },
      { id: "bravo", name: "Bravo", added: "2026-09-13" },
      { id: "charlie", name: "Charlie", added: "2026-03-22" },
    ]);
    const user = userEvent.setup();
    renderPage();
    await openMarketplaceList(user);

    await user.click(screen.getByText("Added"));
    expect(renderedOrder(NAMES)).toEqual(["Bravo", "Charlie", "Alpha"]);

    await user.click(screen.getByText("Added"));
    expect(renderedOrder(NAMES)).toEqual(["Charlie", "Bravo", "Alpha"]);
  });

  it("shows a dash where no date is known", async () => {
    mockRegistry([{ id: "alpha", name: "Alpha" }]);
    const user = userEvent.setup();
    renderPage();
    await openMarketplaceList(user);

    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("returns to A-Z when Name is picked back up after Added", async () => {
    // Newest-first is the right default for a date column, but it must not
    // leak into the text columns: switching back to Name opens ascending.
    mockRegistry([
      { id: "charlie", name: "Charlie", added: "2026-03-22" },
      { id: "alpha", name: "Alpha", added: "2026-09-13" },
    ]);
    const user = userEvent.setup();
    renderPage();
    await openMarketplaceList(user);

    await user.click(screen.getByText("Added"));
    expect(renderedOrder(NAMES)).toEqual(["Alpha", "Charlie"]);

    await user.click(screen.getByText("Name"));
    expect(renderedOrder(NAMES)).toEqual(["Alpha", "Charlie"]);
  });
});
