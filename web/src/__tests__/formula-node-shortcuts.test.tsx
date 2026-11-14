import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FormulaNodeView } from "@/components/tiptap-template-editor/node-views/FormulaNodeView";

// Esc and empty-node deletion belong to FormulaNodeView, not the lazy panel.
// Keep CodeMirror/API loading out of this test; editor-shortcut-bindings tests
// the real panel's Mod+Enter keymap and Done button separately.
vi.mock("@/components/tiptap-template-editor/components/FormulaEditorPanel", () => ({
  FormulaEditorPanel: () => null,
}));

describe("Formula modal shortcuts", () => {
  // binding: closePicker
  it("closes the formula modal, deleting a formula that was never given an expression", async () => {
    const deleteNode = vi.fn();
    const props = {
      node: { attrs: { expression: "", autoOpen: true } },
      updateAttributes: vi.fn(),
      deleteNode,
    } as unknown as Parameters<typeof FormulaNodeView>[0];
    render(<FormulaNodeView {...props} />);
    const dialog = await screen.findByRole("dialog", { name: "Formula editor" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    fireEvent.keyDown(document.body, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Formula editor" })).toBeNull());
    expect(deleteNode).toHaveBeenCalledTimes(1);
  });
});
