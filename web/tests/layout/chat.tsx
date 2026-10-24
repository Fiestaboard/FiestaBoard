import "../../app/globals.css";

import { Button } from "@fiestaboard/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";

import { SpotlightProvider } from "@/components/ai-spotlight/spotlight-provider";
import { CurrentBoardProvider } from "@/components/current-board-context";
import { GlobalAiChatDrawer } from "@/components/global-ai-chat-drawer";
import { GlobalAiPanelProvider, useGlobalAiPanel } from "@/components/global-ai-panel-context";
import { PageEditorBridgeProvider } from "@/components/page-editor-bridge-context";
import { ScheduleEditorBridgeProvider } from "@/components/schedule-editor-bridge-context";
import { ThemeProvider } from "@/hooks/use-theme";
import i18n from "@/i18n/i18next";

import outputs from "../../src/__tests__/mocks/first-party-outputs.json";
import { chatResponse } from "./chat-stream";

const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
const board = { id: "board", name: "Living room", device_type: "flagship", board_color: "black", enabled: true };
const page = {
  id: "sunset",
  name: "Sunset",
  device_type: "flagship",
  template: ["SUNSET"],
  duration_seconds: 60,
  line_metadata: [],
};
const settingsScenario = new URLSearchParams(window.location.search).get("scenario") === "settings";
const originalFetch = window.fetch;
// No backend or live installation is used by these visual fixtures.
window.fetch = async (input, init) => {
  const url = new URL(input instanceof Request ? input.url : String(input), window.location.href);
  if (!url.pathname.startsWith("/api/")) return originalFetch(input, init);
  const path = url.pathname.slice(4);
  if (path === "/pages/ai/chat") return chatResponse(init?.signal);
  let value: unknown = {};
  if (path === "/settings/ai")
    value = {
      enabled: true,
      providers: [
        {
          id: "example",
          name: "Example provider",
          base_url: "https://example.test/v1",
          api_key: "***",
          models: ["example-model"],
          ...(settingsScenario && { sign_in: { preset: "openrouter" } }),
        },
        ...(settingsScenario
          ? [
              {
                id: "second",
                name: "Local models for development and testing",
                models: ["local-model"],
                base_url: "https://local.test/v1",
              },
            ]
          : []),
      ],
      default_provider_id: "example",
      approval_mode: "ask",
    };
  else if (path === "/settings/board") value = { boards: [board], devices: ["flagship"], board_type: "black" };
  else if (path === "/pages") value = { pages: [page] };
  else if (path === "/plugins") value = { plugins: [] };
  else if (path === "/plugins/registry") value = { entries: [] };
  else if (path === "/schedules") value = { schedules: [] };
  else if (path === "/collections") value = { collections: [] };
  else if (path === "/outputs") value = outputs;
  else if (path.includes("/models"))
    value = {
      models: [
        { id: "example-model", name: "Example model" },
        ...(settingsScenario
          ? Array.from({ length: 100 }, (_, i) => ({
              id: `provider/model-${i}-with-a-long-version-identifier`,
              name: `Reasoning model ${i}`,
            }))
          : []),
      ],
    };
  else if (path === "/templates/render")
    value = {
      rendered:
        "\n{65}{65}{66}{66}{66}{66}{65}{65}\n{65}{66}{66}{67}{67}{66}{66}{65}\n{66}{66}{67}{67}{67}{67}{66}{66}\nGOLDEN HOUR\n",
      lines: [],
      layers: null,
    };
  else if (path.startsWith("/ai/conversations/"))
    value = {
      id: path.split("/").at(-1),
      title: "Sunset",
      messages: [],
      created_at: "2026-01-01T12:00:00Z",
      updated_at: "2026-01-01T12:00:00Z",
    };
  else if (path === "/ai/conversations") value = { conversations: [], total: 0 };
  return Response.json(value);
};

function Fixture() {
  const { open } = useGlobalAiPanel();
  return (
    <>
      <main className="content-root min-h-screen bg-background p-6 text-foreground">
        <h1 className="mb-2 text-2xl font-semibold">Page editor</h1>
        <p className="mb-6 text-muted-foreground">FiestaBot browser layout fixture</p>
        <Button onClick={open}>Open assistant</Button>
        <label className="mt-8 block">
          Page name
          <input className="ml-2 rounded-md border p-2" defaultValue="Sunset" />
        </label>
      </main>
      <GlobalAiChatDrawer />
    </>
  );
}
const theme = new URLSearchParams(window.location.search).get("theme") === "dark" ? "dark" : "light";
localStorage.setItem("theme", theme);
createRoot(document.getElementById("root")!).render(
  <MemoryRouter>
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>
        <ThemeProvider defaultTheme={theme}>
          <ScheduleEditorBridgeProvider>
            <PageEditorBridgeProvider>
              <SpotlightProvider>
                <GlobalAiPanelProvider>
                  <CurrentBoardProvider>
                    <Fixture />
                  </CurrentBoardProvider>
                </GlobalAiPanelProvider>
              </SpotlightProvider>
            </PageEditorBridgeProvider>
          </ScheduleEditorBridgeProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </I18nextProvider>
  </MemoryRouter>,
);
