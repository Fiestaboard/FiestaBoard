/**
 * Per-page transition override picker in the PageBuilder header.
 *
 * The backend has accepted `Page.transition_strategy` (a built-in strategy
 * name, `plugin:<id>`, or null = inherit the global default) for a while; these
 * tests cover the UI that finally reads and writes it. The load-bearing detail
 * is the clear path: clearing back to "Use global default" must send an
 * explicit `null`, because an omitted key leaves the previous override in place
 * on the server.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PageBuilder } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const API_BASE = "/api";

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
}));

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return (
    <QueryClientProvider client={queryClient}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          {children}
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}

/** Serve GET /pages/page-1 with the given saved override. */
function servePageWithTransition(transitionStrategy: string | null) {
  server.use(
    http.get(`${API_BASE}/pages/page-1`, () =>
      HttpResponse.json({
        id: "page-1",
        name: "Weather Page",
        type: "template",
        device_type: "flagship",
        template: ["HELLO", "", "", "", "", ""],
        duration_seconds: 300,
        transition_strategy: transitionStrategy,
        created_at: "2024-01-01T00:00:00Z",
      }),
    ),
  );
}

/** Capture the body of the next PUT /pages/:id. */
function captureUpdate(): { body: Record<string, unknown> | null } {
  const captured: { body: Record<string, unknown> | null } = { body: null };
  server.use(
    http.put(`${API_BASE}/pages/page-1`, async ({ request }) => {
      captured.body = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({
        status: "success",
        page: { id: "page-1", name: "Weather Page", type: "template", device_type: "flagship" },
      });
    }),
  );
  return captured;
}

async function openTransitionMenu(user: ReturnType<typeof userEvent.setup>) {
  const trigger = await screen.findByRole("button", { name: "Page transition" });
  await user.click(trigger);
  return trigger;
}

describe("PageBuilder — per-page transition picker", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("sends the chosen built-in strategy as transition_strategy on save", async () => {
    servePageWithTransition(null);
    const captured = captureUpdate();
    const user = userEvent.setup();

    render(<PageBuilder pageId="page-1" onClose={vi.fn()} />, { wrapper: TestWrapper });

    await openTransitionMenu(user);
    await user.click(await screen.findByRole("menuitemradio", { name: "Diagonal" }));

    await user.click(await screen.findByRole("button", { name: "Save Page" }));

    await waitFor(() => expect(captured.body).not.toBeNull());
    expect(captured.body?.transition_strategy).toBe("diagonal");
  });

  it("sends an explicit null when clearing an existing override back to the global default", async () => {
    servePageWithTransition("column");
    const captured = captureUpdate();
    const user = userEvent.setup();

    render(<PageBuilder pageId="page-1" onClose={vi.fn()} />, { wrapper: TestWrapper });

    await openTransitionMenu(user);
    await user.click(await screen.findByRole("menuitemradio", { name: "Use global default" }));

    await user.click(await screen.findByRole("button", { name: "Save Page" }));

    await waitFor(() => expect(captured.body).not.toBeNull());
    // The key must be PRESENT and null — omitting it leaves the old override
    // in place, since the API only clears fields it is explicitly sent.
    expect(captured.body).toHaveProperty("transition_strategy");
    expect(captured.body?.transition_strategy).toBeNull();
  });

  it("shows the saved override as the selected menu item when the editor loads", async () => {
    servePageWithTransition("edges-to-center");
    const user = userEvent.setup();

    render(<PageBuilder pageId="page-1" onClose={vi.fn()} />, { wrapper: TestWrapper });

    await openTransitionMenu(user);

    expect(await screen.findByRole("menuitemradio", { name: "Curtain", checked: true })).toBeInTheDocument();
    expect(
      await screen.findByRole("menuitemradio", { name: "Use global default", checked: false }),
    ).toBeInTheDocument();
  });

  it("marks the editor dirty when the transition changes", async () => {
    servePageWithTransition(null);
    const user = userEvent.setup();

    render(<PageBuilder pageId="page-1" onClose={vi.fn()} />, { wrapper: TestWrapper });

    // Export is gated on hasUnsavedChanges, so it doubles as a dirty-state probe.
    const exportBtn = await screen.findByRole("button", { name: "Export Page" });
    await waitFor(() => expect(exportBtn).toBeEnabled());

    await openTransitionMenu(user);
    await user.click(await screen.findByRole("menuitemradio", { name: "Row" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Export Page" })).toBeDisabled());
  });

  it("offers installed transition plugins as plugin:<id> once the beta flag is on", async () => {
    servePageWithTransition(null);
    server.use(
      http.get(`${API_BASE}/settings/beta`, () =>
        HttpResponse.json({
          settings: { https_enabled: false, transition_plugins_enabled: true },
          https: { cert_present: false, cert_path: "", key_path: "", updater_available: false },
        }),
      ),
      http.get(`${API_BASE}/transitions/plugins`, () =>
        HttpResponse.json({
          plugins: [{ id: "typewriter", name: "Typewriter", description: "", icon: "", version: "1.0.0" }],
        }),
      ),
    );
    const captured = captureUpdate();
    const user = userEvent.setup();

    render(<PageBuilder pageId="page-1" onClose={vi.fn()} />, { wrapper: TestWrapper });

    await openTransitionMenu(user);
    await user.click(await screen.findByRole("menuitemradio", { name: "Typewriter" }));

    await user.click(await screen.findByRole("button", { name: "Save Page" }));

    await waitFor(() => expect(captured.body).not.toBeNull());
    expect(captured.body?.transition_strategy).toBe("plugin:typewriter");
  });

  it("keeps showing a plugin override by its raw id when the beta flag is off", async () => {
    servePageWithTransition("plugin:typewriter");
    const user = userEvent.setup();

    render(<PageBuilder pageId="page-1" onClose={vi.fn()} />, { wrapper: TestWrapper });

    await openTransitionMenu(user);

    expect(await screen.findByRole("menuitemradio", { name: "typewriter", checked: true })).toBeInTheDocument();
    expect(
      await screen.findByRole("menuitemradio", { name: "Use global default", checked: false }),
    ).toBeInTheDocument();
  });
});
