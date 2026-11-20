/**
 * BB-FC-1, BB-FC-2: Settings type scale and index rows against 07e.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SettingsPage from "../../app/routes/settings";
import { server } from "./mocks/server";

const boardContext = { currentBoardId: "desk", boards: [{ id: "desk", name: "Desk" }], isLoading: false };

vi.mock("@/components/current-board-context", () => ({ useCurrentBoard: () => boardContext }));

vi.mock("@/hooks/use-router", async () => {
  const rr = await vi.importActual<typeof import("react-router")>("react-router");
  return {
    useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), forward: vi.fn() }),
    useSearchParams: () => rr.useSearchParams()[0],
    usePathname: () => "/settings",
    useParams: rr.useParams,
  };
});

vi.mock("@/components/wizard-provider", () => ({ useWizard: () => ({ triggerWizard: vi.fn() }) }));

// The shared setup stubs react-router's location hooks; this reads the real one.
const rrActual = await vi.importActual<typeof import("react-router")>("react-router");

function Where() {
  const location = rrActual.useLocation();
  return <div data-testid="where">{location.pathname + location.search + location.hash}</div>;
}

function renderAt(path: string) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/settings/:section?"
            element={
              <>
                <SettingsPage />
                <Where />
              </>
            }
          />
          <Route path="/displays/desk" element={<div>Desk playback settings</div>} />
          <Route path="/displays" element={<div>Choose a display</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function anchor(id: string): Element | null {
  return document.querySelector(`[data-ai-anchor="${id}"]`);
}

function setPhone(phone: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: phone && query.includes("max-width: 767.98px"),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

const originalMatchMedia = window.matchMedia;

beforeEach(() => {
  boardContext.currentBoardId = "desk";
  boardContext.boards = [{ id: "desk", name: "Desk" }];
  setPhone(false);
  server.use(
    http.get("/api/network/wifi/capability", () => HttpResponse.json({ available: false })),
    http.get("/api/auth/mcp-token", () => HttpResponse.json({ configured: false, source: "none" })),
    http.get("/api/debug/system-info", () =>
      HttpResponse.json({
        board_ip: "192.168.1.1",
        server_ip: "192.168.1.2",
        uptime_seconds: 3600,
        uptime_formatted: "1h 0m",
        connection_mode: "local",
        version: "11.0.0",
        timestamp: "2026-11-13T12:00:00Z",
        cache_status: null,
        board_configured: true,
        service_running: true,
      }),
    ),
    http.get("/api/settings/all", () =>
      HttpResponse.json({ general: { timezone: "America/Los_Angeles", instance_name: "Maya’s FiestaPi" } }),
    ),
  );
});

afterEach(() => {
  window.matchMedia = originalMatchMedia;
});

const classes = (el: Element | null): string[] => (el?.getAttribute("class") ?? "").split(/\s+/);

/*
 * BB-FC-1: a settings section reads at 07e's scale (`320:8881`, `333:56102`,
 * `333:57132`): a Heading/2xl title with only the hub meta under it, and
 * card titles 14/20 with no icon over 12/16 descriptions.
 */
describe("Settings detail type scale (BB-FC-1)", () => {
  it("titles a phone section at 2xl with the hub meta, not a description sentence", async () => {
    setPhone(true);
    renderAt("/settings/system");
    const h1 = await screen.findByRole("heading", { level: 1, name: "System & backups" });
    expect(classes(h1)).toContain("text-2xl");
    expect(screen.queryByText(/Updates, backups and/)).toBeNull();
    const meta = document.querySelector('[data-slot="settings-detail-meta"]');
    await waitFor(() => expect(meta?.textContent).toContain("Maya’s FiestaPi"));
    expect(meta?.textContent).toMatch(/ · /);
    expect(classes(meta)).toContain("text-xs");
  });

  it("draws section cards with a 14px title, no icon, and a 12px description", async () => {
    renderAt("/settings/appearance");
    await screen.findByRole("heading", { level: 2, name: "Appearance" });
    const titles = document.querySelectorAll('[data-slot="settings-detail"] [data-slot="card-title"]');
    expect(titles.length).toBeGreaterThan(0);
    for (const title of titles) {
      expect(classes(title)).toContain("text-sm");
      expect(title.querySelector('[data-slot="card-title-icon"], svg')).toBeNull();
    }
    for (const description of document.querySelectorAll(
      '[data-slot="settings-detail"] [data-slot="page-section"] > div > div > [data-slot="card-description"]',
    )) {
      expect(classes(description)).toContain("text-xs");
    }
  });
});

/*
 * BB-FC-2: index rows sit inset in their card with no dividers (07e
 * `320:7936` "Settings row", desktop `321:9076`), trailing values are
 * Text/xs, and group labels are flush with the card edge.
 */
describe("Settings index rows (BB-FC-2)", () => {
  it("insets rows with no dividers and reads values at xs", async () => {
    renderAt("/settings");
    const you = await screen.findByRole("list", { name: "You" });
    expect(classes(you)).not.toContain("divide-y");
    expect(classes(you)).toContain("p-1");
    expect(classes(you)).toContain("gap-0.5");
    const label = document.getElementById(you.getAttribute("aria-labelledby")!);
    expect(classes(label)).not.toContain("px-1");
    await waitFor(() => expect(you.querySelector('[data-slot="list-row-meta"]')).not.toBeNull());
    for (const meta of you.querySelectorAll('[data-slot="list-row-meta"] > span')) {
      expect(classes(meta)).toContain("text-xs");
    }
    for (const row of within(you).getAllByRole("link")) {
      expect(classes(row)).toContain("rounded-md");
    }
  });

  it("fills the open row edge to edge of the inset row, not 4px further in", async () => {
    renderAt("/settings/appearance");
    const you = await screen.findByRole("list", { name: "You" });
    const open = within(you).getByRole("link", { current: "page" });
    expect(classes(open)).toContain("before:inset-0");
    expect(classes(open)).not.toContain("before:inset-1");
  });
});
