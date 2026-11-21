/**
 * The desktop editor's preview card (BB-E-5, BB-E-6, BB-E-9; Figma 53:137378,
 * 307:46094).
 *
 * - The card states its target once, in the header's mono meta
 *   ("Living Room · Flagship 22 × 6"). That meta is the one control for the
 *   preview target, the board size and the board colour (D3): no live-output
 *   picker inside the card, no detached size and colour row under the template.
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
  it("states the target once, as the header meta, with no picker or size row on the canvas", async () => {
    renderEditor();
    await screen.findByDisplayValue("Existing Page");
    const card = document.getElementById("page-editor-preview")!;
    const target = await within(card).findByRole("button", { name: /Preview on Living Room · Flagship 22 × 6/ });
    expect(target).toBeInTheDocument();
    // The AI walkthrough spotlights the size control through this anchor; it must stay in the DOM.
    expect(resolveAnchor("page-editor.device")).toBe(target);
    expect(screen.queryByRole("combobox", { name: "Select board for live output" })).toBeNull();
    expect(screen.queryByRole("combobox", { name: "Change board size" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Preview as black board" })).toBeNull();
  });

  it("opens target, size and colour from the meta", async () => {
    const user = userEvent.setup();
    renderEditor();
    await screen.findByDisplayValue("Existing Page");
    const card = document.getElementById("page-editor-preview")!;
    await user.click(await within(card).findByRole("button", { name: /Preview on Living Room/ }));
    const panel = await screen.findByRole("dialog", { name: "Preview target" });
    expect(within(panel).getByRole("combobox", { name: "Select board for live output" })).toBeInTheDocument();
    expect(within(panel).getByRole("combobox", { name: "Change board size" })).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Preview as white board" })).toBeInTheDocument();
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
