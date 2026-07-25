/**
 * TDD for Task 7: PageBuilder wiring of pencil draw mode.
 *
 * Covers the last integration point in the pencil-draw-mode feature: the
 * pencil toggle inside the rich editor's toolbar must flip PageBuilder's
 * `drawMode` state, which (a) hides the rich-text textbox while keeping it
 * mounted, (b) exposes the drawable preview surface, (c) exits on Escape,
 * and (d) round-trips a real stroke commit through
 * `TipTapTemplateEditorHandle.applyStroke` -> the editor's `onUpdate` ->
 * PageBuilder's `onChange` -> `setTemplateLines` -> back into the editor's
 * `value` prop, without the value-sync effect clobbering the just-painted
 * cell (which would happen if that effect didn't skip `setContent` when
 * `value` already matches the editor's serialized content).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PageBuilder } from "@/components/page-builder";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";
import type { BoardSettings, Page } from "@/lib/api";
import { api } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual("@/lib/api");
  return {
    ...actual,
    api: {
      ...(actual as { api: object }).api,
      renderTemplate: vi.fn(),
      renderTemplateLive: vi.fn(),
      getTemplateVariables: vi.fn(),
      createPage: vi.fn(),
      updatePage: vi.fn(),
      getPage: vi.fn(),
      getBoardSettings: vi.fn(),
      forceRefresh: vi.fn(),
    },
  };
});

function TestWrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return (
    <QueryClientProvider client={queryClient}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          {children}
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}

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
  ],
  devices: ["flagship"],
};

describe("PageBuilder draw mode wiring", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getTemplateVariables).mockResolvedValue({
      variables: {},
      max_lengths: {},
      colors: {},
      symbols: [],
      filters: [],
      formatting: {},
      syntax_examples: {},
    });
    vi.mocked(api.renderTemplate).mockResolvedValue({
      rendered: "test preview",
      lines: ["test preview"],
      line_count: 1,
    });
    vi.mocked(api.getBoardSettings).mockResolvedValue(boardSettings);
  });

  it("shows the pencil toggle in rich mode", async () => {
    render(<PageBuilder onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });

    const toggle = await screen.findByTestId("draw-mode-toggle");
    expect(toggle).toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-pressed", "false");
  });

  it("defaults the draw brush to the red color swatch", async () => {
    const user = userEvent.setup();
    render(<PageBuilder onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });

    const toggle = await screen.findByTestId("draw-mode-toggle");
    await user.click(toggle);

    // Default brush is { kind: "color", color: "red" } — the red swatch is
    // pressed, the rest (and the eraser) are not.
    expect(screen.getByTestId("draw-color-red")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("draw-color-blue")).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByTestId("draw-color-eraser")).toHaveAttribute("aria-pressed", "false");
  });

  it("activating draw mode hides the rich-text textbox and shows the draw surface", async () => {
    const user = userEvent.setup();
    const { container } = render(<PageBuilder onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });

    const toggle = await screen.findByTestId("draw-mode-toggle");
    // Not in draw mode yet — no drawable surface, textbox visible.
    expect(container.querySelector('[data-draw-surface="true"]')).toBeNull();
    const textbox = container.querySelector('[role="textbox"]') as HTMLElement;
    expect(textbox).toBeTruthy();
    expect(textbox.closest(".hidden")).toBeNull();

    await user.click(toggle);

    expect(toggle).toHaveAttribute("aria-pressed", "true");
    expect(container.querySelector('[data-draw-surface="true"]')).toBeTruthy();
    // The textbox stays mounted (so applyStroke can keep operating on the
    // live ProseMirror doc) but is visually hidden behind the drawable canvas.
    expect(textbox.closest(".hidden")).toBeTruthy();
  });

  it("exits draw mode on Escape", async () => {
    const user = userEvent.setup();
    const { container } = render(<PageBuilder onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });

    const toggle = await screen.findByTestId("draw-mode-toggle");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "true");

    fireEvent.keyDown(window, { key: "Escape" });

    await waitFor(() => expect(toggle).toHaveAttribute("aria-pressed", "false"));
    const textbox = container.querySelector('[role="textbox"]') as HTMLElement;
    expect(textbox.closest(".hidden")).toBeNull();
    expect(container.querySelector('[data-draw-surface="true"]')).toBeNull();
  });

  it("round-trips a stroke commit through applyStroke -> onChange -> templateLines without clobbering", async () => {
    const user = userEvent.setup();
    const { container } = render(<PageBuilder onClose={vi.fn()} onSave={vi.fn()} />, { wrapper: TestWrapper });

    const toggle = await screen.findByTestId("draw-mode-toggle");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "true");

    // Board tiles carry data-row/data-col regardless of static/animated
    // rendering; DrawableBoardPreview's hit-testing goes through
    // document.elementFromPoint, so point it at a real tile pulled from the
    // rendered board rather than a synthetic detached node.
    const tile = await waitFor(() => {
      const el = container.querySelector('[data-row="0"][data-col="0"]');
      expect(el).toBeTruthy();
      return el as HTMLElement;
    });

    const efpSpy = vi.spyOn(document, "elementFromPoint").mockReturnValue(tile);
    const surface = container.querySelector('[data-draw-surface="true"]') as HTMLElement;
    expect(surface).toBeTruthy();

    fireEvent.pointerDown(surface, { button: 0, pointerId: 1, clientX: 1, clientY: 1 });
    fireEvent.pointerUp(surface, { pointerId: 1 });

    // handleStrokeCommit -> tipTapRef.current.applyStroke(...) mutates the
    // ProseMirror doc directly and fires onUpdate -> onChange ->
    // setTemplateLines, which re-renders the editor with a new `value`.
    // ColorTileNode uses a custom ReactNodeViewRenderer (ColorTileNodeView),
    // so its rendered DOM is the node view's own markup, not the schema's
    // renderHTML() attributes — the reliable hook is the tile's aria-label.
    await waitFor(() => {
      const colorTile = container.querySelector('[aria-label="red color tile"]');
      expect(colorTile).toBeTruthy();
    });

    // Give the value-sync effect (its setContent call is deferred via
    // queueMicrotask) a full turn of the loop, then confirm the painted
    // cell is still there — exactly once. If the effect's `value !==
    // currentSerialized` check were wrong, it would either clobber the
    // paint back to blank or double-apply it in a render loop.
    await new Promise((resolve) => setTimeout(resolve, 20));
    const stableTiles = container.querySelectorAll('[aria-label="red color tile"]');
    expect(stableTiles.length).toBe(1);

    // Exiting draw mode re-reveals the textbox; the paint must survive.
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(toggle).toHaveAttribute("aria-pressed", "false"));
    expect(container.querySelector('[aria-label="red color tile"]')).toBeTruthy();

    efpSpy.mockRestore();
  });
});

/**
 * Committing a stroke forces the painted rows to left alignment with wrap
 * off (painted lines are positional). That metadata lives in React state,
 * outside ProseMirror history — so undoing the stroke must restore the
 * captured pre-stroke alignment/wrap, and redoing it must re-force
 * left/no-wrap. Observed through the renderTemplate preview payload, which
 * carries the line metadata the server would use.
 */
describe("PageBuilder draw mode undo restores line metadata", () => {
  const centeredPage: Page = {
    id: "page-1",
    name: "Centered Page",
    type: "template",
    device_type: "flagship",
    template: ["HELLO", "", "", "", "", ""],
    line_metadata: [
      { alignment: "center", wrap: true },
      { alignment: "left", wrap: false },
      { alignment: "left", wrap: false },
      { alignment: "left", wrap: false },
      { alignment: "left", wrap: false },
      { alignment: "left", wrap: false },
    ],
    duration_seconds: 30,
    created_at: "2026-01-01T00:00:00Z",
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getTemplateVariables).mockResolvedValue({
      variables: {},
      max_lengths: {},
      colors: {},
      symbols: [],
      filters: [],
      formatting: {},
      syntax_examples: {},
    });
    vi.mocked(api.renderTemplate).mockResolvedValue({
      rendered: "test preview",
      lines: ["test preview"],
      line_count: 1,
    });
    vi.mocked(api.getBoardSettings).mockResolvedValue(boardSettings);
    vi.mocked(api.getPage).mockResolvedValue(centeredPage);
  });

  /** Enter draw mode and commit a single-cell stroke at (0,0) with the default red brush. */
  async function paintTopLeftCell(container: HTMLElement) {
    const user = userEvent.setup();
    const toggle = await screen.findByTestId("draw-mode-toggle");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "true");

    const tile = await waitFor(() => {
      const el = container.querySelector('[data-row="0"][data-col="0"]');
      expect(el).toBeTruthy();
      return el as HTMLElement;
    });
    const efpSpy = vi.spyOn(document, "elementFromPoint").mockReturnValue(tile);
    const surface = container.querySelector('[data-draw-surface="true"]') as HTMLElement;
    expect(surface).toBeTruthy();

    fireEvent.pointerDown(surface, { button: 0, pointerId: 1, clientX: 1, clientY: 1 });
    fireEvent.pointerUp(surface, { pointerId: 1 });
    efpSpy.mockRestore();
  }

  async function waitForLastRender(line0: string, alignment: string, wrap: boolean) {
    await waitFor(
      () => {
        const last = vi.mocked(api.renderTemplate).mock.calls.at(-1);
        expect(last).toBeTruthy();
        expect(last![0][0]).toBe(line0);
        expect(last![1][0]).toEqual({ alignment, wrap });
      },
      { timeout: 4000 },
    );
  }

  it("undoing a stroke restores the painted row's pre-stroke alignment and wrap", async () => {
    const { container } = render(<PageBuilder pageId="page-1" onClose={vi.fn()} onSave={vi.fn()} />, {
      wrapper: TestWrapper,
    });

    await paintTopLeftCell(container);

    // The commit forced row 0 to left/no-wrap.
    await waitForLastRender("{{red}}ELLO", "left", false);

    // Undo (draw-mode keyboard path) rewinds the doc AND the metadata.
    fireEvent.keyDown(window, { key: "z", ctrlKey: true });
    await waitForLastRender("HELLO", "center", true);
  });

  it("redoing a stroke re-forces left alignment and wrap off", async () => {
    const { container } = render(<PageBuilder pageId="page-1" onClose={vi.fn()} onSave={vi.fn()} />, {
      wrapper: TestWrapper,
    });

    await paintTopLeftCell(container);
    await waitForLastRender("{{red}}ELLO", "left", false);

    fireEvent.keyDown(window, { key: "z", ctrlKey: true });
    await waitForLastRender("HELLO", "center", true);

    fireEvent.keyDown(window, { key: "z", ctrlKey: true, shiftKey: true });
    await waitForLastRender("{{red}}ELLO", "left", false);
  });
});
