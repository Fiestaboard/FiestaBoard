/**
 * The desktop editor's preview card (BB-E-5, BB-E-6, BB-E-9; Figma 53:137378,
 * 307:46094).
 *
 * - The card states its target once, in the header's mono meta
 *   ("Living Room · Flagship 22 × 6"). On a saved page it is plain text: the
 *   display is Inspector › Shows on's, the board colour is ⋯ View's (D3,
 *   DD-W159). A new page (no Inspector yet) keeps the meta as the popover for
 *   the target, the size and the colour.
 * - Under the board: Mirror and Replay only.
 * - The board never flaps while you edit (D7); Replay plays the cascade.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const boardProps = vi.fn();
vi.mock("@/components/scaled-board-display", async () => {
  const actual = await vi.importActual<typeof import("@/components/scaled-board-display")>(
    "@/components/scaled-board-display",
  );
  return {
    ...actual,
    ScaledBoardDisplay: (props: Record<string, unknown>) => {
      boardProps(props);
      return (
        <actual.ScaledBoardDisplay {...(props as unknown as React.ComponentProps<typeof actual.ScaledBoardDisplay>)} />
      );
    },
  };
});

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual("@/lib/api");
  return {
    ...actual,
    api: {
      ...(actual as { api: object }).api,
      renderTemplate: vi.fn(),
      renderTemplateLive: vi.fn(),
      getTemplateVariables: vi.fn(),
      getPage: vi.fn(),
      getBoardSettings: vi.fn(),
    },
  };
});

import { PageBuilder } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import { resolveAnchor } from "@/lib/ai-choreography/anchors";
import type { BoardSettings, Page } from "@/lib/api";
import { api } from "@/lib/api";

const boardSettings: BoardSettings = {
  board_type: "black",
  boards: [
    {
      id: "board-1",
      name: "Living Room",
      device_type: "flagship",
      board_color: "black",
      enabled: true,
      api_mode: "local",
      host: "192.168.1.100",
      local_api_key: "test-key",
      cloud_key: "",
    },
    {
      id: "board-2",
      name: "Hallway",
      device_type: "note",
      board_color: "white",
      enabled: true,
      api_mode: "local",
      host: "192.168.1.101",
      local_api_key: "test-key",
      cloud_key: "",
    },
  ],
  devices: ["flagship", "note"],
};

const page: Page = {
  id: "existing-1",
  revision: "r1",
  name: "Existing Page",
  type: "template",
  device_type: "flagship",
  template: ["HELLO", "", "", "", "", ""],
  duration_seconds: 300,
  created_at: new Date().toISOString(),
};

function renderEditor() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          <PageBuilder pageId="existing-1" onClose={vi.fn()} />
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(api.getTemplateVariables).mockResolvedValue({
    variables: {},
    max_lengths: {},
    colors: {},
    symbols: [],
    filters: [],
    formatting: {},
    syntax_examples: {},
  });
  vi.mocked(api.renderTemplate).mockResolvedValue({ rendered: "HELLO", lines: ["HELLO"], line_count: 1 });
  vi.mocked(api.getBoardSettings).mockResolvedValue(boardSettings);
  vi.mocked(api.getPage).mockResolvedValue(page);
});

describe("Preview card (BB-E-5, BB-E-6)", () => {
  it("states a saved page's target once, as plain-text meta: no popup, no picker or size row (D3, DD-W159)", async () => {
    renderEditor();
    await screen.findByDisplayValue("Existing Page");
    const card = document.getElementById("page-editor-preview")!;
    const meta = await within(card).findByTestId("preview-target-meta");
    expect(meta).toHaveTextContent("Living Room · Flagship 22 × 6");
    expect(meta).toHaveAttribute("title", "Living Room · Flagship 22 × 6");
    expect(meta.closest("button")).toBeNull();
    expect(meta).toHaveClass("truncate", "min-w-0");
    // The AI walkthrough spotlights the page's display through this anchor; it stays in the DOM.
    expect(resolveAnchor("page-editor.device")).toBe(meta);
    // Inspector › Shows on is the one display picker; the in-place resize of #1250 is retired.
    expect(screen.queryByTestId("preview-target-trigger")).toBeNull();
    expect(screen.queryByRole("button", { name: /Preview on/ })).toBeNull();
    expect(screen.queryByRole("combobox", { name: "Select board for live output" })).toBeNull();
    expect(screen.queryByRole("combobox", { name: "Change board size" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Preview as black board" })).toBeNull();
  });

  it("offers a saved page's board colour in ⋯ View, and the choice closes the menu", async () => {
    const user = userEvent.setup();
    renderEditor();
    await screen.findByDisplayValue("Existing Page");
    const card = document.getElementById("page-editor-preview")!;
    await user.click(within(card).getByRole("button", { name: "View" }));
    const menu = await screen.findByRole("menu");
    const colour = within(menu).getByRole("group", { name: "Board color" });
    expect(within(colour).getByRole("menuitemradio", { name: "Black" })).toHaveAttribute("aria-checked", "true");
    await user.click(within(colour).getByRole("menuitemradio", { name: "White" }));
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
    await waitFor(() => expect(boardProps.mock.lastCall![0]).toMatchObject({ boardType: "white" }));
  });

  it("opens Fit by default on a Flagship pane (UX-4-2); a stored choice still wins", async () => {
    const user = userEvent.setup();
    const { unmount } = renderEditor();
    await screen.findByDisplayValue("Existing Page");
    const card = document.getElementById("page-editor-preview")!;
    await user.click(within(card).getByRole("button", { name: "View" }));
    expect(await screen.findByRole("menuitemradio", { name: /^Fit/ })).toHaveAttribute("aria-checked", "true");
    await user.click(screen.getByRole("menuitemradio", { name: /^Actual size/ }));
    unmount();
    renderEditor();
    await screen.findByDisplayValue("Existing Page");
    await user.click(within(document.getElementById("page-editor-preview")!).getByRole("button", { name: "View" }));
    expect(await screen.findByRole("menuitemradio", { name: /^Actual size/ })).toHaveAttribute("aria-checked", "true");
  });

  it("keeps the target popover (board, size, colour) on a new page until it has an Inspector", async () => {
    const user = userEvent.setup();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <ConfigOverridesProvider>
          <ThemeProvider attribute="class" defaultTheme="light">
            <PageBuilder onClose={vi.fn()} />
          </ThemeProvider>
        </ConfigOverridesProvider>
      </QueryClientProvider>,
    );
    const trigger = await screen.findByRole("button", { name: /Preview on Living Room/ });
    const card = document.getElementById("page-editor-preview")!;
    expect(card).toContainElement(trigger);
    expect(resolveAnchor("page-editor.device")).toBe(trigger);
    await user.click(trigger);
    const panel = await screen.findByRole("dialog", { name: "Preview target" });
    expect(within(panel).getByRole("combobox", { name: "Select board for live output" })).toBeInTheDocument();
    expect(within(panel).getByRole("combobox", { name: "Change board size" })).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Preview as white board" })).toBeInTheDocument();
    // One place per fact: the new page's colour is the popover's, not View's too.
    await user.keyboard("{Escape}");
    const view = within(card).queryByRole("button", { name: "View" });
    if (view) {
      await user.click(view);
      expect(within(await screen.findByRole("menu")).queryByRole("group", { name: "Board color" })).toBeNull();
    }
  });

  it("puts Replay beside Mirror", async () => {
    renderEditor();
    await screen.findByDisplayValue("Existing Page");
    const card = document.getElementById("page-editor-preview")!;
    const live = card.querySelector('[data-slot="editor-preview-live"]')!;
    expect(within(live as HTMLElement).getByRole("button", { name: "Replay" })).toBeInTheDocument();
  });
});

describe("Preview animation (BB-E-9, D7)", () => {
  it("does not animate edits, and Replay plays the cascade", async () => {
    const user = userEvent.setup();
    type Frame = { message: string | null; animate: boolean };
    const frames = (from = 0) => boardProps.mock.calls.slice(from).map(([p]) => p as Frame);
    renderEditor();
    await screen.findByDisplayValue("Existing Page");
    // Wait for the rendered preview before pressing Replay. The template
    // render is debounced, so the board first shows a loading (null) message.
    // Replay plays whatever the board shows when it is pressed, and any later
    // change to the message ends the replay and snaps (D7). If Replay is
    // pressed while the board is still loading, the debounced "HELLO" lands
    // mid-replay and ends it. That only happens when the runner is slow, which
    // is how this test used to flake.
    await waitFor(() => expect(boardProps.mock.lastCall![0]).toMatchObject({ message: "HELLO" }));
    // The rendered preview arrived without flapping: edits snap.
    expect(frames().every((p) => !p.animate)).toBe(true);
    const card = document.getElementById("page-editor-preview")!;
    const beforeReplay = boardProps.mock.calls.length;
    await user.click(within(card).getByRole("button", { name: "Replay" }));
    await waitFor(() => expect(boardProps.mock.lastCall![0]).toMatchObject({ message: "HELLO", animate: true }));
    // The cascade starts from a blank board with animations on.
    expect(frames(beforeReplay).some((p) => p.message === "" && p.animate)).toBe(true);
  });
});
