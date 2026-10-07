/**
 * Plugin updates live on the Integrations section now, not in Settings. The
 * section header carries one action, "Check for updates" (the same shape as
 * Displays' "Add a display"). The auto-update switch is a setting of the
 * installed plugins, so it sits on the Installed tab's toolbar row beside the
 * plugins it acts on, and carries the AI walkthrough's `settings.plugins`
 * anchors.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { IntegrationsSection } from "../../app/routes/integrations";
import IntegrationsPage from "../../app/routes/integrations._index";
import { server } from "./mocks/server";

const API_BASE = "/api";

const toastMock = vi.hoisted(() => ({ success: vi.fn(), info: vi.fn(), error: vi.fn(), warning: vi.fn() }));

vi.mock("sonner", () => ({ toast: toastMock, Toaster: () => null }));

vi.mock("@/hooks/use-router", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/hooks/use-router")>()),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
  useParams: () => ({}),
}));

vi.mock("@/components/smart-link", () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <IntegrationsSection>
        <IntegrationsPage />
      </IntegrationsSection>
    </QueryClientProvider>,
  );
}

const header = () => document.querySelector<HTMLElement>("[data-slot=page-header]")!;
const anchor = (id: string) => document.querySelector<HTMLElement>(`[data-ai-anchor="${id}"]`);

let saved: unknown[] = [];

beforeEach(() => {
  saved = [];
  toastMock.success.mockReset();
  toastMock.error.mockReset();
  server.use(
    http.get(`${API_BASE}/plugins`, () =>
      HttpResponse.json({ plugins: [], plugin_system_enabled: true, total: 0, enabled_count: 0 }),
    ),
    http.get(`${API_BASE}/plugins/registry`, () => HttpResponse.json({ entries: [] })),
    http.get(`${API_BASE}/settings/plugins`, () => HttpResponse.json({ auto_update: true })),
    http.put(`${API_BASE}/settings/plugins`, async ({ request }) => {
      const body = await request.json();
      saved.push(body);
      return HttpResponse.json(body);
    }),
  );
});

describe("Integrations section — plugin updates", () => {
  it("keeps only Check for updates in the section header", async () => {
    renderPage();
    // Wait for the switch to load wherever it lives, so its absence from the
    // header is not just the settings request still being in flight.
    await screen.findByRole("switch", { name: "Auto-update plugins" });
    expect(within(header()).getByRole("button", { name: /check for updates/i })).toBeInTheDocument();
    expect(within(header()).queryByRole("switch")).not.toBeInTheDocument();
  });

  it("shows the auto-update switch on the Installed tab's toolbar", async () => {
    renderPage();
    const toggle = await screen.findByRole("switch", { name: "Auto-update plugins" });
    await waitFor(() => expect(toggle).toBeChecked());
    expect(toggle.closest("[data-slot=page-toolbar]")).not.toBeNull();
  });

  it("saves auto-update when the switch is turned off", async () => {
    const user = userEvent.setup();
    renderPage();
    const toggle = await screen.findByRole("switch", { name: "Auto-update plugins" });
    await waitFor(() => expect(toggle).toBeChecked());

    await user.click(toggle);

    await waitFor(() => expect(saved).toEqual([{ auto_update: false }]));
    await waitFor(() => expect(toastMock.success).toHaveBeenCalled());
  });

  it("hides the auto-update switch on the Marketplace tab", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("switch", { name: "Auto-update plugins" });

    await user.click(screen.getByRole("tab", { name: /marketplace/i }));

    await waitFor(() => expect(screen.queryByRole("switch", { name: "Auto-update plugins" })).not.toBeInTheDocument());
  });

  it("lands the AI walkthrough's plugin-settings anchors on the toolbar, not the header", async () => {
    renderPage();
    const toggle = await screen.findByRole("switch", { name: "Auto-update plugins" });
    expect(anchor("settings.plugins.auto_update")).toBe(toggle);
    const card = anchor("settings.plugins");
    expect(card).not.toBeNull();
    expect(card).toContainElement(toggle);
    expect(header()).not.toContainElement(card);
  });
});
