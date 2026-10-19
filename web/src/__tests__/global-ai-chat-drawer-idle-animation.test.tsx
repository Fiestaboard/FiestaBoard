/**
 * The AI drawer is mounted on every route and only slid off-screen when
 * closed. Its sparkle animates `background-position`, which cannot run on the
 * compositor, so while it runs the browser does a full main-thread frame 60
 * times a second, for the whole page. On board-heavy pages (/displays, /pages,
 * home) that was ~15-20% of the main thread with nothing happening.
 *
 * globals.css pauses the sparkle under `[data-ai-drawer="closed"]`; these
 * tests pin the DOM contract that selector relies on.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";

import { SpotlightProvider } from "@/components/ai-spotlight/spotlight-provider";
import { CurrentBoardProvider } from "@/components/current-board-context";
import { GlobalAiPanelProvider, useGlobalAiPanel } from "@/components/global-ai-panel-context";
import { PageEditorBridgeProvider } from "@/components/page-editor-bridge-context";
import { ScheduleEditorBridgeProvider } from "@/components/schedule-editor-bridge-context";
import { SidebarProvider } from "@/components/sidebar-context";
import type { ChatTurnContext } from "@/lib/ai-chat-types";

import { server } from "./mocks/server";

vi.mock("@/hooks/use-router", () => ({
  usePathname: () => "/displays",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
}));

const chatContext = vi.hoisted(() => ({ get: null as null | (() => ChatTurnContext) }));
vi.mock("@/components/ai-chat-panel", async () => {
  const actual = await vi.importActual<typeof import("@/components/ai-chat-panel")>("@/components/ai-chat-panel");
  return {
    ...actual,
    AiChatPanel: (props: React.ComponentProps<typeof actual.AiChatPanel>) => {
      chatContext.get = props.getTurnContext;
      return createElement(actual.AiChatPanel, props);
    },
  };
});

// Must import after mocking.
import { GlobalAiChatDrawer } from "@/components/global-ai-chat-drawer";

const PAUSED_SPARKLE = '[data-ai-drawer="closed"] .ai-sparkle-icon';

let openPanel: () => void = () => {};
function CaptureOpen() {
  openPanel = useGlobalAiPanel().open;
  return null;
}

function renderDrawer() {
  server.use(
    http.get("/api/plugins", () => HttpResponse.json({ plugins: [] })),
    http.get("/api/plugins/registry", () => HttpResponse.json({ entries: [] })),
    http.get("/api/settings/ai", () =>
      HttpResponse.json({
        enabled: true,
        providers: [{ id: "p1", name: "Test", base_url: "https://example.test/v1", api_key: "***", models: ["m"] }],
        default_provider_id: "p1",
        approval_mode: "ask",
      }),
    ),
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ScheduleEditorBridgeProvider>
        <PageEditorBridgeProvider>
          <SpotlightProvider>
            <GlobalAiPanelProvider>
              <SidebarProvider>
                <CurrentBoardProvider>
                  <CaptureOpen />
                  <GlobalAiChatDrawer />
                </CurrentBoardProvider>
              </SidebarProvider>
            </GlobalAiPanelProvider>
          </SpotlightProvider>
        </PageEditorBridgeProvider>
      </ScheduleEditorBridgeProvider>
    </QueryClientProvider>,
  );
}

describe("AI drawer sparkle while closed", () => {
  it("puts the closed drawer's sparkle under the selector that pauses it", async () => {
    const { container } = renderDrawer();

    await waitFor(() => expect(container.querySelector(PAUSED_SPARKLE)).not.toBeNull());
  });

  it("lets the sparkle run once the drawer opens", async () => {
    const { container } = renderDrawer();
    await waitFor(() => expect(container.querySelector(".ai-sparkle-icon")).not.toBeNull());

    act(() => openPanel());

    await waitFor(() => expect(container.querySelector('[data-ai-drawer="open"] .ai-sparkle-icon')).not.toBeNull());
    expect(container.querySelector(PAUSED_SPARKLE)).toBeNull();
  });
});

it("uses the selected panel type in the next chat turn", async () => {
  server.use(
    http.get("/api/settings/board", () =>
      HttpResponse.json({
        board_type: "black",
        devices: ["panel"],
        boards: [
          {
            id: "pixels",
            name: "Pixels",
            device_type: "panel",
            board_color: "black",
            enabled: true,
            grid_rows: 10,
            grid_cols: 16,
          },
        ],
      }),
    ),
  );
  renderDrawer();
  await waitFor(() => expect(chatContext.get?.()).toMatchObject({ deviceType: "panel", boardId: "pixels" }));
});
