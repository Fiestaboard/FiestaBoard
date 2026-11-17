/**
 * Plugin previews honor the board's code-62 flap (issue #1666).
 *
 * `BoardInstance.code62_glyph` says whether a Flagship's character-code-62 flap
 * carries a degree sign or a heart (issue #1657), and the dashboard, editor and
 * wizard all pass it down. The Integrations surfaces did not: the marketplace
 * card's teaser strip and the detail page's hero showcase were handed
 * `boardType` and nothing else, so a plugin whose teaser puts a temperature on
 * the board advertised a `°` to owners whose board physically draws a `♥`.
 *
 * The registry fixtures below are the manifest fixture the issue asks for — no
 * shipped manifest puts code 62 in a `teaser` or `previews` yet, which is the
 * only reason the gap was latent rather than visible.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";
import type { Code62Glyph } from "@/lib/api";

import IntegrationsPage from "../../app/routes/integrations._index";
import PluginDetailPage from "../../app/routes/integrations.$pluginId";
import { server } from "./mocks/server";

const API_BASE = "/api";

// Only `useParams` is faked — the detail route reads the plugin id from it and
// there is no router around these renders. The rest of the module (notably
// `useSearchParams`, which the Integrations page reads its tab from) stays real.
vi.mock("@/hooks/use-router", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/hooks/use-router")>()),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
  useParams: () => ({ pluginId: "weather" }),
}));

vi.mock("@/components/smart-link", () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

/** A board whose code-62 flap carries `glyph`; omit for a board saved before the setting existed. */
function mockBoard(glyph?: Code62Glyph) {
  server.use(
    http.get(`${API_BASE}/settings/board`, () =>
      HttpResponse.json({
        board_type: "black",
        boards: [
          {
            id: "default",
            name: "Flagship",
            device_type: "flagship",
            board_color: "black",
            ...(glyph ? { code62_glyph: glyph } : {}),
            enabled: true,
          },
        ],
        devices: ["flagship"],
      }),
    ),
  );
}

/** One uninstalled registry plugin whose teaser and previews put code 62 on the board. */
function mockWeatherRegistry(
  teaser = "52 °F CLEAR",
  {
    installed = false,
    previews = [{ device_type: "flagship", rows: [teaser] }],
  }: { installed?: boolean; previews?: Array<{ device_type: string; rows: string[] }> } = {},
) {
  const plugin = {
    id: "weather",
    name: "Weather",
    description: "Current conditions on your board",
    category: "weather",
    version: "1.0.0",
    author: "FiestaBoard",
    enabled: true,
    configured: true,
    plugin_type: "data",
    icon: "cloud",
    source: { source_type: "registry" },
    config: {},
    update_available: false,
  };
  server.use(
    http.get(`${API_BASE}/plugins`, () =>
      HttpResponse.json({
        plugins: installed ? [plugin] : [],
        plugin_system_enabled: true,
        total: installed ? 1 : 0,
        enabled_count: installed ? 1 : 0,
      }),
    ),
    http.get(`${API_BASE}/plugins/registry`, () =>
      HttpResponse.json({
        entries: [
          {
            id: "weather",
            name: "Weather",
            description: "Current conditions on your board",
            category: "weather",
            repository: "https://example.com/weather",
            branch: "main",
            author: "FiestaBoard",
            fiestaboard_version: ">=8.0.0",
            icon: "puzzle",
            installed,
            teaser,
            previews,
          },
        ],
      }),
    ),
    http.get(`${API_BASE}/v1/plugins/weather`, () =>
      HttpResponse.json({
        ...plugin,
        settings_schema: { type: "object", properties: {} },
        variables: {},
        env_vars: [],
        documentation: null,
      }),
    ),
    http.get(`${API_BASE}/v1/plugins/weather/data`, () => HttpResponse.json({ available: false, data: {} })),
    http.get(`${API_BASE}/oauth/connections`, () => HttpResponse.json({ connections: [] })),
  );
}

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

/** Marketplace tab, card view — where a registry entry renders its teaser strip. */
async function openMarketplaceCards() {
  const user = userEvent.setup();
  await user.click(await screen.findByRole("tab", { name: /marketplace/i }));
}

describe("Integrations plugin previews — code-62 flap", () => {
  it("draws a heart in the marketplace teaser when the board's flap carries one", async () => {
    mockBoard("heart");
    mockWeatherRegistry();
    renderWithQueryClient(<IntegrationsPage />);

    await openMarketplaceCards();

    // The strip hides its tiles from assistive tech, so its role="img" name is
    // the derivation of what the tiles drew — tiles and name come from the same
    // substitution and cannot disagree.
    expect(await screen.findByRole("img", { name: /52 ♥F CLEAR/ })).toBeInTheDocument();
  });

  it("keeps the degree in the marketplace teaser for a board saved before the setting", async () => {
    mockBoard();
    mockWeatherRegistry();
    renderWithQueryClient(<IntegrationsPage />);

    await openMarketplaceCards();

    expect(await screen.findByRole("img", { name: /52 °F CLEAR/ })).toBeInTheDocument();
  });

  it("draws a heart in the plugin detail showcase when the board's flap carries one", async () => {
    mockBoard("heart");
    mockWeatherRegistry();
    renderWithQueryClient(<PluginDetailPage />);

    // Blank tiles draw nothing, so the board's text is the glyphs with the
    // padding squeezed out.
    const board = await screen.findByRole("img", { name: /split-flap board/i });
    expect(board).toHaveTextContent("52♥FCLEAR");
  });

  it("keeps the degree in the plugin detail showcase for a board saved before the setting", async () => {
    mockBoard();
    mockWeatherRegistry();
    renderWithQueryClient(<PluginDetailPage />);

    const board = await screen.findByRole("img", { name: /split-flap board/i });
    expect(board).toHaveTextContent("52°FCLEAR");
  });
});

/**
 * A teaser written in extended markup draws its split-flap degradation
 * (FiestaUI #336): the span's letters without the colour, the icon as its
 * fallback tile, which has no letters to name. Before, the strip spelled the
 * markers out ("{RED:52} ... {ICON:SUN}").
 */
describe("Integrations plugin previews — extended markup on a split-flap board", () => {
  it("draws a span's letters and an icon's tile in the marketplace teaser", async () => {
    mockBoard("heart");
    mockWeatherRegistry("{red:52} °F {icon:sun}");
    renderWithQueryClient(<IntegrationsPage />);

    await openMarketplaceCards();

    const strip = await screen.findByRole("img", { name: /52 ♥F/ });
    expect(strip).not.toHaveAccessibleName(/RED|ICON/);
  });

  it("draws a span's letters in the plugin detail showcase", async () => {
    mockBoard("heart");
    mockWeatherRegistry("{red:52} °F {icon:sun}");
    renderWithQueryClient(<PluginDetailPage />);

    const board = await screen.findByRole("img", { name: /split-flap board/i });
    expect(board).toHaveTextContent("52♥F");
    expect(board).not.toHaveTextContent(/RED|ICON/);
  });
});

afterEach(() => {
  localStorage.removeItem("fiestaboard_current_board");
  vi.unstubAllGlobals();
});

describe("Installed integration board previews", () => {
  it("keeps the installed sample available in the selected desktop detail pane", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query === "(min-width: 768px)",
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    mockBoard("heart");
    mockWeatherRegistry("52 °F CLEAR", { installed: true });
    renderWithQueryClient(<IntegrationsPage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /^Weather/ }));
    const detail = screen.getByRole("complementary", { name: "Integration settings" });
    const board = await within(detail).findByRole("img", { name: /split-flap board/i });
    expect(board).toHaveTextContent("52♥FCLEAR");
    expect(within(detail).getByRole("group", { name: "Board color" })).toBeInTheDocument();
  });

  it("preserves the showcase and its controls using the selected board’s color and code-62 glyph", async () => {
    mockWeatherRegistry("52 °F CLEAR", {
      installed: true,
      previews: [
        { device_type: "flagship", rows: ["52 °F CLEAR"] },
        { device_type: "note", rows: ["NOTE FORECAST"] },
      ],
    });
    localStorage.setItem("fiestaboard_current_board", "selected");
    server.use(
      http.get(`${API_BASE}/settings/board`, async () => {
        await delay(50);
        return HttpResponse.json({
          board_type: "black",
          devices: ["flagship"],
          boards: [
            {
              id: "primary",
              name: "Primary",
              device_type: "flagship",
              board_color: "black",
              code62_glyph: "degree",
              enabled: true,
            },
            {
              id: "selected",
              name: "Selected",
              device_type: "flagship",
              board_color: "white",
              code62_glyph: "heart",
              enabled: true,
            },
          ],
        });
      }),
    );
    renderWithQueryClient(
      <CurrentBoardProvider>
        <PluginDetailPage />
      </CurrentBoardProvider>,
    );
    const board = await screen.findByRole("img", { name: /split-flap board/i });
    await waitFor(() => expect(board).toHaveTextContent("52♥FCLEAR"));
    const colors = screen.getByRole("group", { name: "Board color" });
    await waitFor(() =>
      expect(within(colors).getByRole("button", { name: "White Board" })).toHaveAttribute("aria-pressed", "true"),
    );
    const user = userEvent.setup();
    await user.click(within(colors).getByRole("button", { name: "Black Board" }));
    expect(within(colors).getByRole("button", { name: "Black Board" })).toHaveAttribute("aria-pressed", "true");
    const shapes = screen.getByRole("tablist", { name: "Board shape" });
    await user.click(within(shapes).getByRole("tab", { name: /Note/ }));
    expect(await screen.findByRole("img", { name: /split-flap board/i })).toHaveTextContent("NOTEFORECAST");
    expect(screen.getByRole("tab", { name: "Settings" })).toBeInTheDocument();
  });

  it("retains the degree fallback for an installed plugin when the board setting predates code-62", async () => {
    mockBoard();
    mockWeatherRegistry("52 °F CLEAR", { installed: true });
    renderWithQueryClient(<PluginDetailPage />);
    expect(await screen.findByRole("img", { name: /split-flap board/i })).toHaveTextContent("52°FCLEAR");
  });

  it("does not invent a showcase when an installed registry entry has no previews", async () => {
    mockBoard("heart");
    mockWeatherRegistry("52 °F CLEAR", { installed: true, previews: [] });
    renderWithQueryClient(<PluginDetailPage />);
    await screen.findByText("No configuration options available for this plugin.");
    expect(document.querySelector('[data-slot="board-showcase"]')).toBeNull();
    expect(screen.queryByRole("group", { name: "Board color" })).not.toBeInTheDocument();
  });
});
