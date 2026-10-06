/**
 * The Settings tabs after the reshuffle: MQTT joins General, Behavior is
 * renamed Scheduling, Integrations is renamed AI (AI providers and MCP only),
 * plugin updates move to the Integrations page, and the About card leaves
 * System (the About box in the account menu replaces it). Old
 * `?section=behavior` / `?section=integrations` links still land on the tab
 * that now holds their cards.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsPage from "../../app/routes/settings";
import { server } from "./mocks/server";

const search = { value: "" };

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), forward: vi.fn() }),
  useSearchParams: () => new URLSearchParams(search.value),
  usePathname: () => "/settings",
}));

vi.mock("@/components/wizard-provider", () => ({ useWizard: () => ({ triggerWizard: vi.fn() }) }));

function renderAt(query: string) {
  search.value = query;
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[`/settings?${query}`]}>
        <Routes>
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function anchor(id: string): Element | null {
  return document.querySelector(`[data-ai-anchor="${id}"]`);
}

beforeEach(() => {
  server.use(http.get("/api/network/wifi/capability", () => HttpResponse.json({ available: false })));
});

describe("Settings tabs", () => {
  it("lists Scheduling and AI in place of Behavior and Integrations", async () => {
    renderAt("section=general");
    expect(await screen.findByRole("tab", { name: "Scheduling" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "AI" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Behavior" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Integrations" })).not.toBeInTheDocument();
  });

  it("an old ?section=behavior link opens the Scheduling tab", async () => {
    renderAt("section=behavior");
    expect(await screen.findByRole("tab", { name: "Scheduling", selected: true })).toBeInTheDocument();
  });

  it("an old ?section=integrations link opens the AI tab", async () => {
    renderAt("section=integrations");
    expect(await screen.findByRole("tab", { name: "AI", selected: true })).toBeInTheDocument();
  });

  it("shows MQTT on the General tab", async () => {
    renderAt("section=general");
    await waitFor(() => expect(anchor("settings.mqtt")).not.toBeNull());
  });

  it("keeps the AI tab to AI providers and MCP", async () => {
    renderAt("section=ai");
    await waitFor(() => expect(anchor("settings.ai")).not.toBeNull());
    expect(anchor("settings.mqtt")).toBeNull();
    expect(anchor("settings.plugins")).toBeNull();
  });

  it("no longer shows an About card on the System tab", async () => {
    renderAt("section=system");
    expect(await screen.findByRole("tab", { name: "System", selected: true })).toBeInTheDocument();
    expect(screen.queryByText("About This FiestaBoard")).not.toBeInTheDocument();
  });
});
