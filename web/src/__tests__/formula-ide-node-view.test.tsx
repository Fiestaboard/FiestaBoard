import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { type FormulaIdeBridge, FormulaIdeContext } from "@/components/formula-ide/formula-ide-context";
import { FormulaNodeView } from "@/components/tiptap-template-editor/node-views/FormulaNodeView";

vi.mock("@/components/tiptap-template-editor/components/FormulaEditorPanel", () => ({
  FormulaEditorPanel: () => null,
}));

const EXPR = 'IF(weather.temp > 80, "HOT", "NICE")';

function renderChip(
  bridge: FormulaIdeBridge | null,
  updateAttributes = vi.fn(),
  extra: { editor?: unknown; getPos?: () => number; expression?: string } = {},
) {
  const props = {
    node: { attrs: { expression: extra.expression ?? EXPR, autoOpen: false }, nodeSize: 1 },
    updateAttributes,
    deleteNode: vi.fn(),
    editor: extra.editor,
    getPos: extra.getPos,
  } as unknown as Parameters<typeof FormulaNodeView>[0];
  return render(
    <FormulaIdeContext.Provider value={bridge}>
      <FormulaNodeView {...props} />
    </FormulaIdeContext.Provider>,
  );
}

function bridge(overrides: Partial<FormulaIdeBridge> = {}): FormulaIdeBridge {
  return {
    hint: () => ({ line: 3, start: 0, value: { kind: "rows", shown: 3, wanted: 7 }, state: "ok" }),
    openFormula: vi.fn(() => true),
    inspectFormula: vi.fn(),
    ...overrides,
  };
}

describe("FormulaNodeView with the formula IDE", () => {
  it("shows the chip's H5 value as a FormulaAtom", () => {
    renderChip(bridge());
    expect(screen.getByTestId("formula-atom-chip")).toHaveTextContent("= 3 of 7 rows");
  });

  it("shows its source as written inside the uppercase editor surface (BB-FP-10)", () => {
    renderChip(bridge());
    expect(screen.getByTestId("formula-atom-chip").className).toMatch(/\bnormal-case\b/);
  });

  it("keeps the plain pill without a provider", () => {
    renderChip(null);
    expect(screen.queryByTestId("formula-atom-chip")).toBeNull();
  });

  it("opens the docked editor and writes the edit back to the node", () => {
    const ide = bridge();
    const updateAttributes = vi.fn();
    renderChip(ide, updateAttributes);
    fireEvent.mouseDown(screen.getByTestId("formula-atom-chip"), { button: 0 });
    expect(ide.openFormula).toHaveBeenCalledTimes(1);
    const request = vi.mocked(ide.openFormula).mock.calls[0][0];
    expect(request.expression).toBe(EXPR);
    request.apply("1 + 1");
    expect(updateAttributes).toHaveBeenCalledWith({ expression: "1 + 1" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("puts the caret back after the chip when the docked editor applies (UX-2-5)", async () => {
    vi.useFakeTimers();
    const ide = bridge();
    const focus = vi.fn();
    renderChip(ide, vi.fn(), { editor: { isDestroyed: false, commands: { focus } }, getPos: () => 5 });
    fireEvent.mouseDown(screen.getByTestId("formula-atom-chip"), { button: 0 });
    vi.mocked(ide.openFormula).mock.calls[0][0].apply("1 + 1");
    act(() => vi.runAllTimers());
    expect(focus).toHaveBeenCalledWith(6);
    vi.useRealTimers();
  });

  it("puts the caret back where a new chip was when the docked editor cancels (Esc)", () => {
    vi.useFakeTimers();
    const ide = bridge();
    const focus = vi.fn();
    renderChip(ide, vi.fn(), {
      editor: { isDestroyed: false, commands: { focus } },
      getPos: () => {
        throw new Error("removed");
      },
    });
    fireEvent.mouseDown(screen.getByTestId("formula-atom-chip"), { button: 0 });
    vi.mocked(ide.openFormula).mock.calls[0][0].cancel();
    act(() => vi.runAllTimers());
    expect(focus).toHaveBeenCalledWith();
    vi.useRealTimers();
  });

  it("falls back to its own dialog when there is no docked editor", () => {
    renderChip(bridge({ openFormula: vi.fn(() => false) }));
    fireEvent.mouseDown(screen.getByTestId("formula-atom-chip"), { button: 0 });
    expect(screen.getByRole("dialog", { name: "Formula editor" })).toBeInTheDocument();
  });

  it("inspects on the context menu without opening the editor", () => {
    const ide = bridge();
    renderChip(ide);
    const chip = screen.getByTestId("formula-atom-chip");
    fireEvent.mouseDown(chip, { button: 2 });
    fireEvent.contextMenu(chip);
    expect(ide.inspectFormula).toHaveBeenCalledWith(EXPR);
    expect(ide.openFormula).not.toHaveBeenCalled();
  });

  it("inspects after a touch long-press", () => {
    vi.useFakeTimers();
    try {
      const ide = bridge();
      renderChip(ide);
      const chip = screen.getByTestId("formula-atom-chip");
      fireEvent.pointerDown(chip, { pointerType: "touch", clientX: 5, clientY: 5 });
      act(() => {
        vi.advanceTimersByTime(500);
      });
      expect(ide.inspectFormula).toHaveBeenCalledWith(EXPR);
      // The compatibility mousedown after the long-press does not open the editor.
      fireEvent.mouseDown(chip, { button: 0 });
      expect(ide.openFormula).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("inspects with Shift+F10 from the keyboard", () => {
    const ide = bridge();
    renderChip(ide);
    fireEvent.keyDown(screen.getByTestId("formula-atom-chip"), { key: "F10", shiftKey: true });
    expect(ide.inspectFormula).toHaveBeenCalledWith(EXPR);
  });
});
