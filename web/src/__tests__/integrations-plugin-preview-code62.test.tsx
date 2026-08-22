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
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

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
function mockWeatherRegistry() {
  server.use(
    http.get(`${API_BASE}/plugins`, () =>
      HttpResponse.json({ plugins: [], plugin_system_enabled: true, total: 0, enabled_count: 0 }),
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
            installed: false,
            teaser: "52 °F CLEAR",
            previews: [{ device_type: "flagship", rows: ["52 °F CLEAR"] }],
          },
        ],
      }),
    ),
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
