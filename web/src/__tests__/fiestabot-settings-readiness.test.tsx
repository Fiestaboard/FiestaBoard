import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { SpotlightProvider } from "@/components/ai-spotlight/spotlight-provider";
import { CurrentBoardProvider } from "@/components/current-board-context";
import { GlobalAiChatDrawer } from "@/components/global-ai-chat-drawer";
import { GlobalAiPanelProvider } from "@/components/global-ai-panel-context";
import { PageEditorBridgeProvider } from "@/components/page-editor-bridge-context";
import { ScheduleEditorBridgeProvider } from "@/components/schedule-editor-bridge-context";
import { FiestaBotSettings } from "@/components/settings/fiestabot-settings";
import { SidebarProvider } from "@/components/sidebar-context";
import type { AISettings } from "@/lib/api";

import { server } from "./mocks/server";

// Use the real router so the setup action proves its actual route destination.
vi.mock("react-router", async () => vi.importActual<typeof import("react-router")>("react-router"));

const READY: AISettings = {
  enabled: true,
  providers: [
    { id: "example", name: "Example", base_url: "https://example.test/v1", api_key: "***", models: ["example-model"] },
  ],
  default_provider_id: "example",
  approval_mode: "ask",
  max_model_calls: null,
  max_tool_calls: null,
};

function renderSettings() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  server.use(
    http.get("/api/plugins", () => HttpResponse.json({ plugins: [] })),
    http.get("/api/plugins/registry", () => HttpResponse.json({ entries: [] })),
  );
  const result = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/settings/fiestabot"]}>
        <ScheduleEditorBridgeProvider>
          <PageEditorBridgeProvider>
            <SpotlightProvider>
              <GlobalAiPanelProvider>
                <SidebarProvider>
                  <CurrentBoardProvider>
                    <Routes>
                      <Route path="/settings/fiestabot" element={<FiestaBotSettings />} />
                      <Route path="/settings/ai-provider" element={<div>AI provider setup destination</div>} />
                    </Routes>
                    <GlobalAiChatDrawer />
                  </CurrentBoardProvider>
                </SidebarProvider>
              </GlobalAiPanelProvider>
            </SpotlightProvider>
          </PageEditorBridgeProvider>
        </ScheduleEditorBridgeProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...result, client };
}

function settingsResponse(settings: AISettings) {
  server.use(http.get("/api/settings/ai", () => HttpResponse.json(settings)));
}

describe("FiestaBot Settings with the actual global drawer", () => {
  it.each([
    { name: "fresh disabled hub", settings: { ...READY, enabled: false, providers: [], default_provider_id: null } },
    { name: "disabled configured hub", settings: { ...READY, enabled: false } },
    { name: "enabled unconfigured hub", settings: { ...READY, providers: [], default_provider_id: null } },
  ])("routes a $name to provider setup instead of a dead drawer action", async ({ settings }) => {
    settingsResponse(settings);
    renderSettings();
    const setup = await screen.findByRole("link", { name: "Set up AI provider" });
    expect(screen.getByText("FiestaBot needs AI enabled and a configured provider on this hub.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open FiestaBot" })).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "FiestaBot AI chat" })).not.toBeInTheDocument();
    await userEvent.click(setup);
    expect(await screen.findByText("AI provider setup destination")).toBeInTheDocument();
  });

  it("opens the actual configured drawer and follows its close guard when AI is disabled", async () => {
    settingsResponse(READY);
    const { client, container } = renderSettings();
    await userEvent.click(await screen.findByRole("button", { name: "Open FiestaBot" }));
    expect(await screen.findByRole("dialog", { name: "FiestaBot AI chat" })).toBeInTheDocument();
    await waitFor(() => expect(container.querySelector('[data-ai-drawer="open"]')).not.toBeNull());
    act(() => client.setQueryData(["ai-settings"], { ...READY, enabled: false }));
    await waitFor(() => expect(container.querySelector('[data-ai-drawer="open"]')).toBeNull());
    expect(screen.queryByRole("dialog", { name: "FiestaBot AI chat" })).not.toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Set up AI provider" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open FiestaBot" })).not.toBeInTheDocument();
  });

  it("does not offer Open while readiness is still loading", async () => {
    let respond!: () => void;
    const pending = new Promise<void>((resolve) => {
      respond = resolve;
    });
    server.use(
      http.get("/api/settings/ai", async () => {
        await pending;
        return HttpResponse.json(READY);
      }),
    );
    renderSettings();
    expect(screen.getByText("Checking FiestaBot availability…")).toHaveAttribute("role", "status");
    expect(screen.queryByRole("button", { name: "Open FiestaBot" })).not.toBeInTheDocument();
    respond();
    expect(await screen.findByRole("button", { name: "Open FiestaBot" })).toBeInTheDocument();
  });

  it("shows a retryable lookup error without offering a dead Open action", async () => {
    let fails = true;
    server.use(
      http.get("/api/settings/ai", () =>
        fails ? HttpResponse.json({ detail: "Example connection failure" }, { status: 503 }) : HttpResponse.json(READY),
      ),
    );
    renderSettings();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not check FiestaBot availability.");
    expect(screen.queryByRole("button", { name: "Open FiestaBot" })).not.toBeInTheDocument();
    fails = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await userEvent.click(await screen.findByRole("button", { name: "Open FiestaBot" }));
    expect(await screen.findByRole("dialog", { name: "FiestaBot AI chat" })).toBeInTheDocument();
  });
});
