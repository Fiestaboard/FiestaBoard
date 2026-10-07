/**
 * Displays → Marketplace: every display FiestaBoard can drive, browsable
 * the way Integrations → Marketplace browses plugins (the same `PluginCard`),
 * so people can see displays are expandable.
 *
 * Pinned here: one card per output `GET /outputs/available` offers (the ones
 * on this FiestaBoard, then the ones ready to install); Install with no
 * opt-in (display plugins need none since settings v7); Update for an
 * installed display plugin with an update; "Add a display" from a card opens
 * the add flow at that display's setup step, and so does a card's link
 * (`/displays?tab=marketplace&add=<id>`); a way to write your own.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DisplaysPage from "../../app/routes/displays._index";
import { mockOutputs } from "./mocks/handlers";
import { server } from "./mocks/server";

const push = vi.fn();
const replace = vi.fn();
let search = new URLSearchParams("tab=marketplace");

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push, replace, back: vi.fn(), forward: vi.fn() }),
  useParams: () => ({}),
  usePathname: () => "/displays",
  useSearchParams: () => search,
}));

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMock, Toaster: () => null }));

const API = "/api";

type Available = {
  id: string;
  name: string;
  description: string;
  icon: string | null;
  source: "installed" | "seed" | "registry";
  installed: boolean;
  builtin: boolean;
  beta_gated: boolean;
  available: boolean;
  needs_network: boolean;
  output_api: number | null;
};

function available(id: string, name: string, source: Available["source"], extra: Partial<Available> = {}): Available {
  return {
    id,
    name,
    description: `${name} description`,
    icon: null,
    source,
    installed: source === "installed",
    builtin: false,
    beta_gated: false,
    available: true,
    needs_network: source === "registry",
    output_api: source === "registry" ? null : 1,
    ...extra,
  };
}

const VESTABOARD = available("vestaboard", "Vestaboard", "installed", { builtin: true, output_api: null });
const FIESTAPANEL = available("fiestapanel", "FiestaPanel", "installed", { builtin: true, output_api: null });
const PIXOO = available("divoom_pixoo", "Divoom Pixoo", "seed");
const ACME = available("acme_sign", "Acme Sign", "registry");

function setup({ outputs = [VESTABOARD, FIESTAPANEL, PIXOO, ACME], updates = {} as Record<string, boolean> } = {}) {
  const calls = { install: [] as string[], update: [] as string[] };
  let listed = outputs;
  server.use(
    http.get(`${API}/settings/board`, () => HttpResponse.json({ board_type: "black", boards: [], devices: [] })),
    http.get(`${API}/outputs`, () => HttpResponse.json(mockOutputs)),
    http.get(`${API}/outputs/available`, () => HttpResponse.json(listed)),
    http.post(`${API}/outputs/:id/install`, ({ params }) => {
      const id = String(params.id);
      calls.install.push(id);
      listed = listed.map((o) => (o.id === id ? { ...o, source: "installed", installed: true } : o));
      return HttpResponse.json({ ...mockOutputs[0], id, name: id, builtin: false }, { status: 201 });
    }),
    http.get(`${API}/plugins/registry`, () =>
      HttpResponse.json({
        plugin_system_enabled: true,
        entries: [
          {
            id: "acme_sign",
            name: "Acme Sign",
            description: "Acme Sign description",
            repository: "https://github.com/example/fiestaboard-output--acme-sign",
            branch: "main",
            author: "Example Author",
            fiestaboard_version: ">=10.0.0",
            icon: "monitor",
            category: "output",
            installed: false,
            plugin_type: "output",
            teaser: "",
            previews: [],
          },
        ],
      }),
    ),
    http.get(`${API}/plugins`, () =>
      HttpResponse.json({
        plugins: Object.entries(updates).map(([id, update_available]) => ({
          id,
          name: id,
          version: "1.0.0",
          description: "",
          author: "",
          enabled: false,
          configured: false,
          icon: "monitor",
          category: "output",
          plugin_type: "output",
          config: {},
          source: { source_type: "registry" },
          update_available,
          instance_label: null,
          base_plugin_id: id,
          settings_schema: {},
        })),
        plugin_system_enabled: true,
        total: Object.keys(updates).length,
        enabled_count: 0,
      }),
    ),
    http.post(`${API}/plugins/:id/update`, ({ params }) => {
      calls.update.push(String(params.id));
      return HttpResponse.json({ plugin_id: params.id, message: "updated" });
    }),
  );
  return calls;
}

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DisplaysPage />
    </QueryClientProvider>,
  );
}

async function marketplace(): Promise<HTMLElement> {
  return screen.findByTestId("display-marketplace");
}

async function cardFor(name: string): Promise<HTMLElement> {
  const market = await marketplace();
  const heading = await within(market).findByRole("heading", { name });
  const card = heading.closest("[data-slot='plugin-card']");
  if (!card) throw new Error(`No marketplace card for ${name}`);
  return card as HTMLElement;
}

beforeEach(() => {
  push.mockReset();
  replace.mockReset();
  toastMock.success.mockReset();
  toastMock.error.mockReset();
  search = new URLSearchParams("tab=marketplace");
});

describe("Displays → Marketplace", () => {
  it("shows a card for every display FiestaBoard can drive, installed ones first", async () => {
    setup();
    renderPage();
    const market = await marketplace();
    const installed = await within(market).findByRole("region", { name: "On this FiestaBoard" });
    const toInstall = within(market).getByRole("region", { name: "Ready to install" });
    expect(
      within(installed)
        .getAllByRole("heading", { level: 3 })
        .map((h) => h.textContent),
    ).toEqual(["Vestaboard", "FiestaPanel"]);
    expect(
      within(toInstall)
        .getAllByRole("heading", { level: 3 })
        .map((h) => h.textContent),
    ).toEqual(["Divoom Pixoo", "Acme Sign"]);
  });

  it("credits a marketplace display's author", async () => {
    setup();
    renderPage();
    expect(within(await cardFor("Acme Sign")).getByText("by Example Author")).toBeInTheDocument();
  });

  it("installs a display with no opt-in", async () => {
    const calls = setup();
    renderPage();
    const card = await cardFor("Acme Sign");
    await userEvent.click(within(card).getByRole("button", { name: "Install Acme Sign" }));
    await waitFor(() => expect(calls.install).toEqual(["acme_sign"]));
    // Installed: the card now offers to add a display with it.
    expect(
      await within(await cardFor("Acme Sign")).findByRole("button", { name: "Add a display with Acme Sign" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/beta/i)).not.toBeInTheDocument();
  });

  it("updates an installed display plugin that has an update", async () => {
    const pixoo = { ...PIXOO, source: "installed" as const, installed: true };
    const calls = setup({ outputs: [VESTABOARD, pixoo], updates: { divoom_pixoo: true } });
    renderPage();
    const card = await cardFor("Divoom Pixoo");
    await userEvent.click(await within(card).findByRole("button", { name: "Update Divoom Pixoo" }));
    await waitFor(() => expect(calls.update).toEqual(["divoom_pixoo"]));
  });

  it("offers no update for a display that is up to date", async () => {
    const pixoo = { ...PIXOO, source: "installed" as const, installed: true };
    setup({ outputs: [pixoo], updates: { divoom_pixoo: false } });
    renderPage();
    const card = await cardFor("Divoom Pixoo");
    expect(within(card).getByRole("button", { name: "Add a display with Divoom Pixoo" })).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: /^Update/ })).not.toBeInTheDocument();
  });

  it("adds a display from its card: the add flow opens at that display's setup", async () => {
    setup();
    renderPage();
    const card = await cardFor("Vestaboard");
    await userEvent.click(within(card).getByRole("button", { name: "Add a display with Vestaboard" }));
    expect(await screen.findByRole("dialog", { name: "Add a Vestaboard" })).toBeInTheDocument();
  });

  it("links each card to its add flow", async () => {
    setup();
    renderPage();
    const card = await cardFor("Acme Sign");
    expect(within(card).getByRole("link", { name: "Acme Sign" })).toHaveAttribute(
      "href",
      "/displays?tab=marketplace&add=acme_sign",
    );
  });

  it("opens the add flow for the display a link names", async () => {
    search = new URLSearchParams("tab=marketplace&add=vestaboard");
    setup();
    renderPage();
    expect(await screen.findByRole("dialog", { name: "Add a Vestaboard" })).toBeInTheDocument();
  });

  it("filters the cards by search", async () => {
    setup();
    renderPage();
    await cardFor("Acme Sign");
    await userEvent.type(screen.getByPlaceholderText("Search displays..."), "pixoo");
    const market = await marketplace();
    await waitFor(() => expect(within(market).queryByRole("heading", { name: "Acme Sign" })).not.toBeInTheDocument());
    expect(within(market).getByRole("heading", { name: "Divoom Pixoo" })).toBeInTheDocument();
  });

  it("shows displays are expandable: a way to write your own", async () => {
    setup();
    renderPage();
    const market = await marketplace();
    expect(within(market).getByRole("link", { name: /Write a display plugin/ })).toHaveAttribute(
      "href",
      "https://fiestaboard.app/docs/development/output-plugins",
    );
  });

  it("the tab strip switches between your displays and the marketplace", async () => {
    search = new URLSearchParams();
    setup();
    renderPage();
    expect(screen.queryByTestId("display-marketplace")).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole("tab", { name: /Marketplace/ }));
    expect(await marketplace()).toBeInTheDocument();
  });
});
