import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { PageEditorBridgeProvider, usePageEditorBridge } from "@/components/page-editor-bridge-context";
import { PageEditorShell } from "@/components/page-editor-shell";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import type { ToolCall, ToolResult } from "@/lib/ai-chat-types";
import { resolveAnchor } from "@/lib/ai-choreography/anchors";
import { runSteps } from "@/lib/ai-choreography/engine";
import { getScript } from "@/lib/ai-choreography/registry";
import type { ChoreographyContext, Step } from "@/lib/ai-choreography/types";
import type { Page } from "@/lib/api";

import { server } from "./mocks/server";

vi.unmock("react-router");

const SKY = {
  id: "sky",
  area: { row: 1, col: 1, rows: 2, cols: 4 },
  bleed: [],
  scale: 1,
  text: "hide" as const,
  content: { background: "#000000", palette: {}, shapes: [], pixels: [] },
};
let savedPage: Page;

beforeEach(() => {
  localStorage.clear();
  savedPage = {
    id: "pixel-page",
    name: "Pixel page",
    type: "template",
    device_type: "panel",
    grid_rows: 10,
    grid_cols: 16,
    template: ["Original text", ...Array(9).fill("")],
    line_metadata: Array.from({ length: 10 }, () => ({ alignment: "left", wrap: false })),
    canvases: [SKY],
    duration_seconds: 30,
    created_at: "2026-01-01T00:00:00Z",
  };
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
            api_mode: "virtual",
            output: "divoom_pixoo",
            device_model: "divoom_pixoo64",
            charset: "led_3x5",
          },
        ],
      }),
    ),
    http.get("/api/panels", () => HttpResponse.json({ panels: [], total: 0 })),
    http.get("/api/v1/pages/pixel-page", () => HttpResponse.json(savedPage)),
  );
});

const CALL: ToolCall = {
  id: "update-text",
  name: "update_page",
  args: { page_id: "pixel-page", template_lines: ["AI text"] },
  title: "Update page",
  read_only: false,
  destructive: false,
  requires_approval: false,
  source: "mcp",
};
const OK: ToolResult = { id: CALL.id, name: CALL.name, status: "ok", summary: "Updated", result: {}, error: null };

async function setup() {
  let bridge!: ReturnType<typeof usePageEditorBridge>;
  function Editor() {
    bridge = usePageEditorBridge();
    return <PageEditorShell pageId="pixel-page" onClose={() => {}} onSave={() => {}} />;
  }
  const router = createMemoryRouter([{ path: "/pages/edit/pixel-page", element: <Editor /> }], {
    initialEntries: ["/pages/edit/pixel-page"],
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <CurrentBoardProvider>
        <ConfigOverridesProvider>
          <ThemeProvider attribute="class" defaultTheme="light">
            <PageEditorBridgeProvider>
              <RouterProvider router={router} />
            </PageEditorBridgeProvider>
          </ThemeProvider>
        </ConfigOverridesProvider>
      </CurrentBoardProvider>
    </QueryClientProvider>,
  );
  const user = userEvent.setup();
  await screen.findByDisplayValue("Pixel page");
  await user.click(screen.getByRole("button", { name: "Plain Text" }));
  await waitFor(() => expect(bridge.staging.isMounted()).toBe(true));
  const shown: Array<{ caption: string; visible: boolean }> = [];
  const pulses: boolean[] = [];
  const ctx: ChoreographyContext = {
    navigate: (href) => {
      void router.navigate(href);
    },
    pathname: () => router.state.location.pathname,
    pageEditor: bridge.staging,
    spotlight: {
      show: ({ anchor, caption }) => {
        shown.push({ caption, visible: !!resolveAnchor(anchor) });
      },
      pulse: (anchor) => {
        pulses.push(!!resolveAnchor(anchor));
      },
      caption: () => {},
      hide: () => {},
      ghost: () => {},
      clearGhosts: () => {},
    },
    schedule: {
      isMounted: () => false,
      openEmpty: () => {},
      openEntry: () => {},
      setField: () => {},
      close: () => {},
      waitFor: async () => false,
      waitForForm: async () => false,
    },
    t: (key) => key,
    label: (call) => call.title,
    reducedMotion: true,
  };
  const play = async (steps: Step[]) => {
    let playing!: Promise<void>;
    act(() => {
      playing = runSteps(steps, ctx, { signal: new AbortController().signal, isFast: () => true });
    });
    await act(async () => {
      await playing;
    });
  };
  return { user, bridge, ctx, shown, pulses, play };
}

it("reveals Text before the AI spotlight and staged text update when a clean editor shows Canvases", async () => {
  const { user, ctx, shown, pulses, play } = await setup();
  await user.click(screen.getByRole("button", { name: "Canvases" }));
  expect(resolveAnchor("page-editor.template")).toBeNull();
  await play(getScript("update_page").narrate(CALL, ctx));
  expect(shown).toContainEqual({ caption: "typingLines", visible: true });
  expect(screen.getByRole("button", { name: "Text" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("textbox", { name: "" })).toHaveValue(["AI text", ...Array(9).fill("")].join("\n"));
  expect(screen.getByRole("button", { name: "Save Page" })).toBeDisabled();
  savedPage = { ...savedPage, template: ["AI text"] };
  await play(getScript("update_page").settle(CALL, OK, ctx));
  expect(pulses).toEqual([true]);
  await waitFor(() => expect(screen.getByRole("button", { name: "Save Page" })).toBeEnabled());
});

it("shows the dirty-draft notice from Canvases and retains every draft value after the AI succeeds", async () => {
  const { user, bridge, ctx, shown, pulses, play } = await setup();
  fireEvent.change(screen.getByRole("textbox", { name: "" }), { target: { value: "My unsaved text" } });
  await user.click(screen.getByRole("button", { name: "Canvases" }));
  fireEvent.change(screen.getByLabelText("Canvas ID"), { target: { value: "my-sky" } });
  await waitFor(() => expect(bridge.staging.hasUnsavedChanges()).toBe(true));
  const draft = bridge.getEditorSnapshot();
  expect(resolveAnchor("page-editor.template")).toBeNull();
  await play(getScript("update_page").narrate(CALL, ctx));
  expect(shown).toContainEqual({ caption: "updatingBehindEdits", visible: true });
  expect(bridge.getEditorSnapshot()).toEqual(draft);
  expect(screen.getByRole("button", { name: "Save Page" })).toBeEnabled();
  savedPage = { ...savedPage, name: "AI saved name", template: ["AI text"] };
  await play(getScript("update_page").settle(CALL, OK, ctx));
  expect(pulses).toEqual([true]);
  expect(bridge.getEditorSnapshot()).toEqual(draft);
  await play(getScript("update_page").stop!(CALL, ctx));
  expect(bridge.getEditorSnapshot()).toEqual(draft);
  expect(bridge.staging.hasUnsavedChanges()).toBe(true);
});
