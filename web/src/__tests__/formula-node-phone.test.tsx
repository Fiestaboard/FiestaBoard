/**
 * BB-B-15 (Figma 306:38107 Formula sheet, 307:45424 Inspect): on a phone a
 * formula opens in a bottom sheet, not a centred modal; Inspect is a button in
 * that sheet, not only a 500 ms long-press; and the caret goes back into the
 * template after Done or Cancel, so typing carries on.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { type FormulaIdeBridge, FormulaIdeContext } from "@/components/formula-ide/formula-ide-context";
import { FormulaNodeView } from "@/components/tiptap-template-editor/node-views/FormulaNodeView";

vi.mock("@/components/tiptap-template-editor/components/FormulaEditorPanel", () => ({
  FormulaEditorPanel: ({ onConfirm, onCancel }: { onConfirm: (e: string) => void; onCancel?: () => void }) => (
    <>
      <button type="button" onClick={() => onConfirm("1 + 1")}>
        Done
      </button>
      <button type="button" onClick={() => onCancel?.()}>
        Cancel
      </button>
    </>
  ),
}));

const EXPR = 'IF(weather.temp > 80, "HOT", "NICE")';

function setPhone(phone: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: phone && query.includes("max-width: 639px"),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

const original = window.matchMedia;
afterEach(() => {
  window.matchMedia = original;
});

function renderChip({ expression = EXPR, bridge = null as FormulaIdeBridge | null } = {}) {
  const focus = vi.fn();
  const props = {
    node: { attrs: { expression, autoOpen: false }, nodeSize: 1 },
    updateAttributes: vi.fn(),
    deleteNode: vi.fn(),
    getPos: () => 12,
    editor: { isDestroyed: false, commands: { focus } },
  } as unknown as Parameters<typeof FormulaNodeView>[0];
  render(
    <FormulaIdeContext.Provider value={bridge}>
      <FormulaNodeView {...props} />
    </FormulaIdeContext.Provider>,
  );
  return { focus, props };
}

const chip = () => screen.getByRole("button", { name: /IF\(weather|= /i });

async function openOnPhone(bridge: FormulaIdeBridge | null = null) {
  setPhone(true);
  const result = renderChip({ bridge });
  fireEvent.mouseDown(screen.getAllByRole("button")[0], { button: 0 });
  await screen.findByRole("dialog", { name: "Formula editor" });
  return result;
}

describe("phone formula editing", () => {
  it("opens a bottom sheet, not a centred modal", async () => {
    await openOnPhone();
    const dialog = screen.getByRole("dialog", { name: "Formula editor" });
    expect(dialog).toHaveAttribute("data-slot", "sheet-content");
    expect(dialog).toHaveAttribute("data-side", "bottom");
  });

  it("keeps the centred dialog from 640px", () => {
    setPhone(false);
    renderChip();
    fireEvent.mouseDown(screen.getAllByRole("button")[0], { button: 0 });
    expect(screen.getByRole("dialog", { name: "Formula editor" })).not.toHaveAttribute("data-slot", "sheet-content");
  });

  it("puts the caret back after the chip on Done", async () => {
    const { focus, props } = await openOnPhone();
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() => expect(focus).toHaveBeenCalledWith(13));
    expect(props.updateAttributes).toHaveBeenCalledWith({ expression: "1 + 1" });
  });

  it("puts the caret back on Cancel", async () => {
    const { focus } = await openOnPhone();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(focus).toHaveBeenCalledWith(13));
  });

  it("offers Inspect in the sheet when the page has the formula IDE", async () => {
    const inspectFormula = vi.fn();
    await openOnPhone({
      hint: () => undefined,
      openFormula: vi.fn(() => false),
      inspectFormula,
    } as unknown as FormulaIdeBridge);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Inspect" }));
    });
    expect(inspectFormula).toHaveBeenCalledWith(EXPR);
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Formula editor" })).toBeNull());
  });
});
