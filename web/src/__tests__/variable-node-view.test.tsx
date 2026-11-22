/**
 * BB-FP-11 (Figma 111:30911 "Atom · weather.temperature"): a variable chip is
 * the kit FormulaAtom (kind variable: 4 px radius, `{}` glyph, 22 px) with the
 * value the page preview sees, not a 13 px dashed pill, and no hover-only
 * "~max length" span nothing could reveal.
 * BB-FP-10 (app half): chips show their source as written, never uppercased by
 * the template editor surface.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { type FormulaIdeBridge, FormulaIdeContext } from "@/components/formula-ide/formula-ide-context";
import { VariableNodeView } from "@/components/tiptap-template-editor/node-views/VariableNodeView";

function renderChip(
  bridge: FormulaIdeBridge | null,
  attrs: Partial<{ pluginId: string; field: string; filters: unknown[]; maxLength: number }> = {},
) {
  const props = {
    node: { attrs: { pluginId: "weather", field: "temperature", filters: [], maxLength: 3, ...attrs } },
  } as unknown as Parameters<typeof VariableNodeView>[0];
  return render(
    <FormulaIdeContext.Provider value={bridge}>
      <VariableNodeView {...props} />
    </FormulaIdeContext.Provider>,
  );
}

function bridge(variableHint: FormulaIdeBridge["variableHint"]): FormulaIdeBridge {
  return { hint: () => undefined, openFormula: vi.fn(() => false), inspectFormula: vi.fn(), variableHint };
}

const atom = () => screen.getByTestId("variable-atom-chip").querySelector('[data-slot="formula-atom"]');

describe("VariableNodeView", () => {
  it("renders the kit variable atom with its source as written", () => {
    renderChip(null);
    const el = atom();
    expect(el).not.toBeNull();
    expect(el).toHaveAttribute("data-kind", "variable");
    expect(el?.querySelector('[data-slot="formula-atom-source"]')).toHaveTextContent("weather.temperature");
    expect(el?.className).not.toMatch(/border-dashed|rounded-full/);
  });

  it("resets the editor surface's uppercase (BB-FP-10)", () => {
    renderChip(null);
    expect(screen.getByTestId("variable-atom-chip").className).toMatch(/\bnormal-case\b/);
  });

  it("shows the value the preview sees for that variable", () => {
    const variableHint = vi.fn(() => ({
      line: 1,
      start: 0,
      value: { kind: "value" as const, text: "62" },
      state: "ok" as const,
    }));
    renderChip(bridge(variableHint));
    expect(variableHint).toHaveBeenCalledWith("weather.temperature");
    expect(atom()?.querySelector('[data-slot="formula-atom-value"]')).toHaveTextContent("= 62");
  });

  it("hides the value segment when nothing has been rendered for it", () => {
    // FiestaUI 8.17.0-alpha.5 (FiestaUI#442): an atom with no value draws no value segment at all.
    for (const b of [bridge(() => undefined), null]) {
      const { unmount } = renderChip(b);
      const el = atom();
      expect(el).not.toBeNull();
      expect(el?.querySelector('[data-slot="formula-atom-value"]')).toBeNull();
      expect(el).toHaveTextContent(/^weather\.temperature$/);
      unmount();
    }
  });

  it("keeps filters in the source as written", () => {
    renderChip(null, { filters: [{ name: "pad", arg: "3" }] });
    expect(atom()?.querySelector('[data-slot="formula-atom-source"]')).toHaveTextContent("weather.temperature|pad:3");
  });

  it("claims no max length the template doesn't carry", () => {
    renderChip(null, { maxLength: 10 });
    expect(screen.queryByText(/Max length/)).toBeNull();
    expect(screen.getByTestId("variable-atom-chip").parentElement).not.toHaveTextContent(/~10/);
  });
});
