import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TemplateEditorToolbar } from "@/components/tiptap-template-editor/components/TemplateEditorToolbar";

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

/**
 * Minimal fake editor: undo/redo available and a non-empty selection, so
 * Undo/Redo/Cut/Copy would all be ENABLED outside draw mode. This makes the
 * lockout assertions meaningful — in draw mode, only the draw-mode contract
 * can be the reason Cut/Copy are disabled, and Undo/Redo staying enabled is
 * positively observable.
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

describe("TemplateEditorToolbar draw mode", () => {
  it("renders the pencil toggle and fires it", () => {
    const onDrawModeToggle = vi.fn();
    renderToolbar({ drawMode: false, onDrawModeToggle, drawBrush: "red", onDrawBrushChange: vi.fn() });
    const toggle = screen.getByTestId("draw-mode-toggle");
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(toggle);
    expect(onDrawModeToggle).toHaveBeenCalled();
  });

  it("hides the brush dropdown when draw mode is off", () => {
    renderToolbar({ drawMode: false, onDrawModeToggle: vi.fn(), drawBrush: "red", onDrawBrushChange: vi.fn() });
    expect(screen.getByTestId("draw-mode-toggle")).toBeInTheDocument();
    expect(screen.queryByTestId("draw-brush-dropdown")).toBeNull();
  });

  it("locks out every content-editing control in draw mode but keeps undo/redo enabled", async () => {
    renderToolbar({
      editor: makeFakeEditor(),
      drawMode: true,
      onDrawModeToggle: vi.fn(),
      drawBrush: "red",
      onDrawBrushChange: vi.fn(),
      onSyncFromBoard: vi.fn(),
    });

    expect(screen.getByTestId("draw-mode-toggle")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("draw-brush-dropdown")).toBeInTheDocument();

    // Clipboard controls
    expect(screen.getByLabelText("Cut")).toBeDisabled();
    expect(screen.getByLabelText("Copy")).toBeDisabled();
    expect(screen.getByLabelText("Paste")).toBeDisabled();

    // Insert dropdowns (render once the template-variables query resolves)
    expect(await screen.findByLabelText("Variables")).toBeDisabled();
    expect(screen.getByLabelText("Colors")).toBeDisabled();
    expect(screen.getByLabelText("Formatting")).toBeDisabled();

    // Formula, wrap, alignment, sync-from-board
    expect(screen.getByLabelText("Insert formula")).toBeDisabled();
    expect(screen.getByLabelText("Toggle wrap for current line")).toBeDisabled();
    expect(screen.getByLabelText("Align left")).toBeDisabled();
    expect(screen.getByLabelText("Align center")).toBeDisabled();
    expect(screen.getByLabelText("Align right")).toBeDisabled();
    expect(screen.getByLabelText("Sync from current board display")).toBeDisabled();

    // Undo/redo stay enabled — the fake editor reports history available
    expect(screen.getByLabelText("Undo")).not.toBeDisabled();
    expect(screen.getByLabelText("Redo")).not.toBeDisabled();
  });

  it("hides the pencil and brush dropdown when no handler is provided", () => {
    renderToolbar({});
    expect(screen.queryByTestId("draw-mode-toggle")).toBeNull();
    expect(screen.queryByTestId("draw-brush-dropdown")).toBeNull();
  });
});
