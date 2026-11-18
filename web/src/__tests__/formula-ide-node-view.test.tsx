import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { type FormulaIdeBridge, FormulaIdeContext } from "@/components/formula-ide/formula-ide-context";
import { FormulaNodeView } from "@/components/tiptap-template-editor/node-views/FormulaNodeView";

vi.mock("@/components/tiptap-template-editor/components/FormulaEditorPanel", () => ({
  FormulaEditorPanel: () => null,
}));

const EXPR = 'IF(weather.temp > 80, "HOT", "NICE")';

function renderChip(bridge: FormulaIdeBridge | null, updateAttributes = vi.fn()) {
  const props = {
    node: { attrs: { expression: EXPR, autoOpen: false } },
    updateAttributes,
    deleteNode: vi.fn(),
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
