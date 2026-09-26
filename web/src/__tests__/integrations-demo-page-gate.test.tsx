/**
 * Create Demo Page must react to a save.
 *
 * The button is gated on `areDemoRequirementsMet()`, which reads the *saved*
 * config out of the sheet's `["plugin", id]` details query — not the form state.
 * That query is configured app-wide with `staleTime: 1 min` (providers.tsx), so
 * unless the save handler invalidates it, reopening the sheet within that minute
 * re-renders the pre-save config and the button stays disabled even though the
 * requirement is now satisfied on disk.
 *
 * Reported against the Horoscope plugin: its only required field was `sign`, so a
 * user who picked a sign and saved still saw "Configure the required settings
 * below before creating a demo page".
 *
 * The QueryClient here mirrors the production staleTime deliberately — with the
 * library default of 0 every remount refetches and the bug cannot reproduce.
 *
 * Both the legacy (`GET /plugins/{id}`, `PUT /plugins/{id}/config`) and v1
 * (`GET`/`PATCH /v1/plugins/{id}`, issue #1930) routes are mocked, so the same
 * assertions run against either routing generation.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import IntegrationsPage from "../../app/routes/integrations._index";
import { server } from "./mocks/server";

const API_BASE = "/api";

const SETTINGS_SCHEMA = {
  type: "object",
  required: ["sign"],
  properties: {
    enabled: { type: "boolean", title: "Enable Horoscope", default: false },
    sign: {
      type: "string",
      title: "Zodiac Sign",
      description: "The sign to show the daily horoscope for",
      enum: ["Aries", "Taurus", "Cancer"],
      default: "Aries",
    },
  },
};

/**
 * One installed plugin whose stored config starts empty and gains `sign` once a
 * save lands — the real backend behaviour, where schema defaults are not
 * materialised into the stored config until something is written.
 */
function mockHoroscope() {
  let config: Record<string, unknown> = {};
  let detailRequests = 0;

  const detail = () => ({
    id: "horoscope",
    name: "Horoscope",
    version: "1.0.0",
    description: "Horoscope description",
    author: "FiestaBoard",
    icon: "sparkles",
    category: "entertainment",
    plugin_type: "data",
    enabled: true,
    config,
    settings_schema: SETTINGS_SCHEMA,
    variables: {},
    max_lengths: {},
    env_vars: [],
    documentation: "README.md",
    has_demo: true,
    demo_page_id: null,
    instance_label: null,
    base_plugin_id: "horoscope",
    instances: [],
  });

  const readDetail = () => {
    detailRequests += 1;
    return HttpResponse.json(detail());
  };

  const writeConfig = async (request: Request) => {
    const body = (await request.json()) as { config: Record<string, unknown> };
    config = body.config;
  };

  server.use(
    http.get(`${API_BASE}/plugins`, () =>
      HttpResponse.json({
        plugins: [
          {
            id: "horoscope",
            name: "Horoscope",
            category: "entertainment",
            version: "1.0.0",
            description: "Horoscope description",
            author: "FiestaBoard",
            enabled: true,
            configured: true,
            icon: "sparkles",
            config,
            source: { source_type: "registry" as const },
            update_available: false,
            instance_label: null,
            base_plugin_id: "horoscope",
            settings_schema: SETTINGS_SCHEMA,
          },
        ],
        plugin_system_enabled: true,
        total: 1,
        enabled_count: 1,
      }),
    ),
    http.get(`${API_BASE}/plugins/registry`, () => HttpResponse.json({ entries: [] })),

    // v1 routes (next)
    http.get(`${API_BASE}/v1/plugins/horoscope`, () => readDetail()),
    http.patch(`${API_BASE}/v1/plugins/horoscope`, async ({ request }) => {
      await writeConfig(request);
      return HttpResponse.json(detail());
    }),

    // legacy routes (main)
    http.get(`${API_BASE}/plugins/horoscope`, () => readDetail()),
    http.put(`${API_BASE}/plugins/horoscope/config`, async ({ request }) => {
      await writeConfig(request);
      return HttpResponse.json({ status: "success", config });
    }),
  );

  return { detailCount: () => detailRequests };
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

async function openConfigSheet(user: ReturnType<typeof userEvent.setup>) {
  await user.click((await screen.findAllByRole("button", { name: /configure/i }))[0]);
  return screen.findByRole("button", { name: /create demo page/i });
}

describe("Integrations — Create Demo Page gate", () => {
  it("disables the button while a required setting is unset", async () => {
    mockHoroscope();
    const user = userEvent.setup();
    renderPage();

    const button = await openConfigSheet(user);
    expect(button).toBeDisabled();
    expect(screen.getByText(/configure the required settings below/i)).toBeInTheDocument();
  });

  it("enables the button after the required setting is saved", async () => {
    mockHoroscope();
    const user = userEvent.setup();
    renderPage();

    const button = await openConfigSheet(user);
    expect(button).toBeDisabled();

    await user.click(await screen.findByRole("button", { name: /save changes/i }));

    // Saving closes the sheet; reopening it must show post-save state rather
    // than the cached pre-save config.
    await waitFor(() => expect(screen.queryByRole("button", { name: /save changes/i })).not.toBeInTheDocument());
    const reopened = await openConfigSheet(user);

    await waitFor(() => expect(reopened).toBeEnabled());
    expect(screen.queryByText(/configure the required settings below/i)).not.toBeInTheDocument();
  });

  it("refetches the plugin details query on save", async () => {
    const { detailCount } = mockHoroscope();
    const user = userEvent.setup();
    renderPage();

    await openConfigSheet(user);
    await waitFor(() => expect(detailCount()).toBe(1));

    await user.click(await screen.findByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(detailCount()).toBeGreaterThan(1));
  });
});
