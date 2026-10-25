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
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
import type { StreamChatHandlers } from "@/lib/api-stream";

import { server } from "./mocks/server";

vi.mock("@/hooks/use-router", () => ({
  usePathname: () => "/displays",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
}));

const transport = vi.hoisted(() => ({
  handlers: null as StreamChatHandlers | null,
  finish: null as (() => void) | null,
  signal: null as AbortSignal | null,
}));
vi.mock("@/lib/api-stream", () => ({
  streamChat: (_body: unknown, handlers: StreamChatHandlers, signal: AbortSignal) =>
    new Promise<void>((resolve) => {
      transport.handlers = handlers;
      transport.finish = resolve;
      transport.signal = signal;
      signal.addEventListener("abort", () => resolve(), { once: true });
    }),
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
  return <button onClick={openPanel}>Open test assistant</button>;
}

function renderDrawer() {
  server.use(
    http.put("/api/ai/conversations/:id", async ({ params, request }) =>
      HttpResponse.json({ ...((await request.json()) as object), id: params.id }),
    ),
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

it("minimizes and restores the same draft without reserving page space", async () => {
  const user = userEvent.setup();
  renderDrawer();
  await waitFor(() => expect(chatContext.get).not.toBeNull());
  const opener = screen.getByRole("button", { name: "Open test assistant" });
  await user.click(opener);
  const input = await screen.findByRole("textbox", { name: "Message" });
  await user.type(input, "Keep this sunset draft");
  await user.click(screen.getByRole("button", { name: "Minimize FiestaBot" }));
  expect(screen.queryByRole("dialog", { name: "FiestaBot AI chat" })).not.toBeInTheDocument();
  expect(document.documentElement).not.toHaveClass("ai-drawer-open");
  const restore = screen.getByRole("button", { name: /Open FiestaBot/ });
  expect(restore).toHaveFocus();
  await user.click(restore);
  expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("Keep this sunset draft");
  expect(screen.getByRole("textbox", { name: "Message" })).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "Close FiestaBot" }));
  expect(screen.queryByRole("button", { name: /Open FiestaBot/ })).not.toBeInTheDocument();
  expect(opener).toHaveFocus();
});

it("removes the hidden drawer controls from keyboard navigation", async () => {
  const { container } = renderDrawer();
  await waitFor(() => expect(container.querySelector('[data-ai-drawer="closed"]')).not.toBeNull());
  expect(container.querySelector('[data-ai-drawer="closed"]')).toHaveAttribute("inert");
});

it("keeps streaming while minimized and announces completion on the restore pill", async () => {
  const user = userEvent.setup();
  renderDrawer();
  act(() => openPanel());
  await user.type(await screen.findByRole("textbox", { name: "Message" }), "Create a sunset");
  await user.click(screen.getByRole("button", { name: "Send" }));
  await user.click(screen.getByRole("button", { name: "Minimize FiestaBot" }));
  expect(transport.signal?.aborted).toBe(false);
  expect(screen.getByRole("button", { name: /Open FiestaBot.*Thinking/ })).toBeInTheDocument();
  act(() => transport.handlers?.onText?.("Your sunset is ready."));
  expect(screen.getByRole("button", { name: /Open FiestaBot.*Writing reply/ })).toBeInTheDocument();
  screen.getByRole("button", { name: "Stop" }).focus();
  await act(async () => {
    transport.handlers?.onDone?.({
      reason: "complete",
      pending_tool_call_id: null,
      model_used: "m",
      provider_id: "p1",
      steps: 0,
      usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
    });
    transport.finish?.();
  });
  expect(screen.getByRole("button", { name: /Open FiestaBot.*Finished/ })).toHaveFocus();
  await user.click(screen.getByRole("button", { name: /Open FiestaBot.*Finished/ }));
  expect(screen.getByText("Your sunset is ready.")).toBeVisible();
});

it("can stop a minimized thinking turn without falsely claiming it finished", async () => {
  const user = userEvent.setup();
  renderDrawer();
  act(() => openPanel());
  await user.type(await screen.findByRole("textbox", { name: "Message" }), "Think about a scene");
  await user.click(screen.getByRole("button", { name: "Send" }));
  await user.click(screen.getByRole("button", { name: "Minimize FiestaBot" }));
  await user.click(screen.getByRole("button", { name: "Stop" }));
  expect(transport.signal?.aborted).toBe(true);
  expect(await screen.findByRole("button", { name: /Open FiestaBot.*Stopped/ })).toHaveFocus();
});
