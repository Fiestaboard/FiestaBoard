/**
 * App-wide Settings excludes board scheduling. MQTT joins General,
 * Integrations is renamed AI (AI providers and MCP only),
 * plugin updates move to the Integrations page, and the About card leaves
 * System (the About box in the account menu replaces it). Old
 * Legacy scheduling links land on the selected display's Playback tab.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsPage from "../../app/routes/settings";
import { server } from "./mocks/server";

const search = { value: "" };
const boardContext = { currentBoardId: "desk", boards: [{ id: "desk", name: "Desk" }], isLoading: false };

vi.mock("@/components/current-board-context", () => ({ useCurrentBoard: () => boardContext }));

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

beforeEach(() => {
  boardContext.currentBoardId = "desk";
  boardContext.boards = [{ id: "desk", name: "Desk" }];
  server.use(http.get("/api/network/wifi/capability", () => HttpResponse.json({ available: false })));
});

describe("Settings tabs", () => {
  it("keeps scheduling out of app-wide settings", async () => {
    renderAt("section=general");
    expect(await screen.findByRole("tab", { name: "AI" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Scheduling" })).not.toBeInTheDocument();
    expect(anchor("settings.polling")).toBeNull();
    expect(anchor("settings.schedule_behavior")).toBeNull();
    expect(screen.queryByRole("tab", { name: "Behavior" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Integrations" })).not.toBeInTheDocument();
  });

  it.each(["behavior", "scheduling"])("an old ?section=%s link opens the current display", async (section) => {
    renderAt(`section=${section}`);
    expect(await screen.findByText("Desk playback settings")).toBeInTheDocument();
  });

  it("an old ?section=integrations link opens the AI tab", async () => {
    renderAt("section=integrations");
    expect(await screen.findByRole("tab", { name: "AI", selected: true })).toBeInTheDocument();
  });

  it("groups General preferences by purpose", async () => {
    renderAt("section=general");
    expect(await screen.findByRole("heading", { name: "Appearance and accessibility" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Language, time and location" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Connections" })).toBeInTheDocument();
  });

  it("keeps preview cadence in a separate Graphics section from appearance preferences", async () => {
    renderAt("section=general");
    const appearanceHeading = await screen.findByRole("heading", { name: "Appearance and accessibility" });
    const appearanceSection = appearanceHeading.closest<HTMLElement>('[data-slot="page-section"]')!;
    await screen.findByRole("radiogroup", { name: "Flip speed" });
    expect(within(appearanceSection).queryByRole("radiogroup", { name: "Flip speed" })).not.toBeInTheDocument();
    const graphicsHeading = screen.getByRole("heading", { name: "Graphics and previews" });
    const graphicsSection = graphicsHeading.closest<HTMLElement>('[data-slot="page-section"]')!;
    expect(within(graphicsSection).getByRole("radiogroup", { name: "Flip speed" })).toBeInTheDocument();
    expect(within(graphicsSection).getByRole("radiogroup", { name: "Board previews" })).toBeInTheDocument();
  });

  it("sends an old scheduling link to the display list when there is no board", async () => {
    boardContext.currentBoardId = "";
    boardContext.boards = [];
    renderAt("section=scheduling");
    expect(await screen.findByText("Choose a display")).toBeInTheDocument();
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
