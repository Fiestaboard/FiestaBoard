import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TemplateEditorToolbar } from "@/components/tiptap-template-editor/components/TemplateEditorToolbar";
import type { DrawBrush } from "@/components/tiptap-template-editor/utils/draw-mode";

vi.mock("@/lib/api", async (importOriginal) => {
  const mod = (await importOriginal()) as Record<string, unknown>;
  return {
    ...mod,
    api: {
      ...(mod.api as Record<string, unknown>),
      getTemplateVariables: vi.fn().mockResolvedValue({
        variables: { x: {} },
        colors: { red: 63 },
        formatting: { bold: {} },
      }),
    },
  };
});

const ALL_COLOR_NAMES = ["red", "orange", "yellow", "green", "blue", "violet", "white", "black"];

/**
 * Minimal fake editor: undo/redo available and a non-empty selection, so
 * Undo/Redo would be ENABLED. In draw mode the content controls must be
 * ABSENT (not merely disabled) while undo/redo stay present and enabled.
 */
function makeFakeEditor() {
  return {
    can: () => ({ undo: () => true, redo: () => true }),
    state: {
      selection: { from: 0, to: 3 },
      doc: { textBetween: () => "abc" },
    },
    on: vi.fn(),
    off: vi.fn(),
  };
}

function renderToolbar(props: Record<string, unknown>) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <TemplateEditorToolbar editor={null} {...props} />
    </QueryClientProvider>,
  );
}

const redBrush: DrawBrush = { kind: "color", color: "red" };

describe("TemplateEditorToolbar draw mode", () => {
  it("renders the pencil toggle and fires it", () => {
    const onDrawModeToggle = vi.fn();
    renderToolbar({ drawMode: false, onDrawModeToggle, drawBrush: redBrush, onDrawBrushChange: vi.fn() });
    const toggle = screen.getByTestId("draw-mode-toggle");
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(toggle);
    expect(onDrawModeToggle).toHaveBeenCalled();
  });

  it("shows no drawing controls when draw mode is off", async () => {
    renderToolbar({ drawMode: false, onDrawModeToggle: vi.fn(), drawBrush: redBrush, onDrawBrushChange: vi.fn() });
    expect(screen.getByTestId("draw-mode-toggle")).toBeInTheDocument();
    for (const name of ALL_COLOR_NAMES) {
      expect(screen.queryByTestId(`draw-color-${name}`)).toBeNull();
    }
    expect(screen.queryByTestId("draw-color-eraser")).toBeNull();
    expect(screen.queryByTestId("draw-char-dropdown")).toBeNull();

    // Normal editing controls stay present
    expect(screen.getByLabelText("Cut")).toBeInTheDocument();
    expect(screen.getByLabelText("Copy")).toBeInTheDocument();
    expect(screen.getByLabelText("Paste")).toBeInTheDocument();
    expect(await screen.findByLabelText("Variables")).toBeInTheDocument();
    expect(screen.getByLabelText("Insert formula")).toBeInTheDocument();
    expect(screen.getByLabelText("Align left")).toBeInTheDocument();
  });

  it("swaps the toolbar in draw mode: content controls absent, swatches/eraser/char dropdown present", () => {
    renderToolbar({
      editor: makeFakeEditor(),
      drawMode: true,
      onDrawModeToggle: vi.fn(),
      drawBrush: redBrush,
      onDrawBrushChange: vi.fn(),
      onSyncFromBoard: vi.fn(),
    });

    expect(screen.getByTestId("draw-mode-toggle")).toHaveAttribute("aria-pressed", "true");

    // Content-editing controls are NOT rendered at all
    expect(screen.queryByLabelText("Cut")).toBeNull();
    expect(screen.queryByLabelText("Copy")).toBeNull();
    expect(screen.queryByLabelText("Paste")).toBeNull();
    expect(screen.queryByLabelText("Variables")).toBeNull();
    expect(screen.queryByLabelText("Colors")).toBeNull();
    expect(screen.queryByLabelText("Formatting")).toBeNull();
    expect(screen.queryByLabelText("Insert formula")).toBeNull();
    expect(screen.queryByLabelText("Toggle wrap for current line")).toBeNull();
    expect(screen.queryByLabelText("Align left")).toBeNull();
    expect(screen.queryByLabelText("Align center")).toBeNull();
    expect(screen.queryByLabelText("Align right")).toBeNull();
    expect(screen.queryByLabelText("Sync from current board display")).toBeNull();

    // All 8 inline color swatches + eraser + character dropdown
    for (const name of ALL_COLOR_NAMES) {
      expect(screen.getByTestId(`draw-color-${name}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId("draw-color-eraser")).toBeInTheDocument();
    expect(screen.getByTestId("draw-char-dropdown")).toBeInTheDocument();

    // Undo/redo stay present and enabled — the fake editor reports history
    expect(screen.getByLabelText("Undo")).not.toBeDisabled();
    expect(screen.getByLabelText("Redo")).not.toBeDisabled();
  });

  it("marks the selected color swatch pressed and fires onDrawBrushChange for others", () => {
    const onDrawBrushChange = vi.fn();
    renderToolbar({
      drawMode: true,
      onDrawModeToggle: vi.fn(),
      drawBrush: redBrush,
      onDrawBrushChange,
    });

    expect(screen.getByTestId("draw-color-red")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("draw-color-blue")).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(screen.getByTestId("draw-color-blue"));
    expect(onDrawBrushChange).toHaveBeenCalledWith({ kind: "color", color: "blue" });
  });

  it("fires the eraser brush and reflects its selection", () => {
    const onDrawBrushChange = vi.fn();
    const { rerender } = renderToolbar({
      drawMode: true,
      onDrawModeToggle: vi.fn(),
      drawBrush: redBrush,
      onDrawBrushChange,
    });

    fireEvent.click(screen.getByTestId("draw-color-eraser"));
    expect(onDrawBrushChange).toHaveBeenCalledWith({ kind: "eraser" });

    const qc = new QueryClient();
    rerender(
      <QueryClientProvider client={qc}>
        <TemplateEditorToolbar
          editor={null}
          drawMode
          onDrawModeToggle={vi.fn()}
          drawBrush={{ kind: "eraser" }}
          onDrawBrushChange={onDrawBrushChange}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("draw-color-eraser")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("draw-color-red")).toHaveAttribute("aria-pressed", "false");
  });

  it("selects a stamp character from the char dropdown", () => {
    const onDrawBrushChange = vi.fn();
    renderToolbar({
      drawMode: true,
      onDrawModeToggle: vi.fn(),
      drawBrush: redBrush,
      onDrawBrushChange,
    });

    fireEvent.click(screen.getByTestId("draw-char-dropdown"));
    const charButton = document.querySelector('[data-draw-char="A"]') as HTMLElement;
    expect(charButton).toBeTruthy();
    fireEvent.click(charButton);
    expect(onDrawBrushChange).toHaveBeenCalledWith({ kind: "char", char: "A" });
    // Selection closes the dropdown
    expect(document.querySelector('[data-draw-char="A"]')).toBeNull();
  });

  it("shows the active stamp character in the dropdown trigger", () => {
    renderToolbar({
      drawMode: true,
      onDrawModeToggle: vi.fn(),
      drawBrush: { kind: "char", char: "H" },
      onDrawBrushChange: vi.fn(),
    });
    expect(screen.getByTestId("draw-char-dropdown")).toHaveTextContent("H");

    fireEvent.click(screen.getByTestId("draw-char-dropdown"));
    const current = document.querySelector('[data-draw-char="H"]') as HTMLElement;
    expect(current).toHaveAttribute("aria-pressed", "true");
  });

  it("hides the pencil and drawing controls when no handler is provided", () => {
    renderToolbar({});
    expect(screen.queryByTestId("draw-mode-toggle")).toBeNull();
    expect(screen.queryByTestId("draw-color-red")).toBeNull();
    expect(screen.queryByTestId("draw-char-dropdown")).toBeNull();
  });
});
