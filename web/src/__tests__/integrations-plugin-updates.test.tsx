/**
 * Plugin updates live on the Integrations section now, not in Settings: the
 * section header carries the auto-update switch beside "Check for updates".
 * It shows on the list; on a plugin's page the header collapses and tucks it
 * away with the rest of the header's action slot.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { IntegrationsSection } from "../../app/routes/integrations";
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
        <p>list</p>
      </IntegrationsSection>
    </QueryClientProvider>,
  );
}

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
  it("shows the auto-update setting in the section header", async () => {
    renderPage();
    const toggle = await screen.findByRole("switch", { name: "Auto-update plugins" });
    await waitFor(() => expect(toggle).toBeChecked());
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

  it("keeps Check for updates next to it", async () => {
    renderPage();
    expect(await screen.findByRole("button", { name: /check for updates/i })).toBeInTheDocument();
  });
});
