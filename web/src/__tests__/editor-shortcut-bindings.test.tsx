/**
 * The `?` list must never describe a key the editor does not bind (slice 2.7).
 * Every listed row names the test that proves its binding, and this file
 * fails if a row is added without one, or if a named test stops mentioning
 * its row. The bindings that live outside PageBuilder are proven here.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "fs";
import path from "path";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { FormulaEditorPanel } from "@/components/tiptap-template-editor/components/FormulaEditorPanel";
import { ToolbarDropdown } from "@/components/tiptap-template-editor/components/ToolbarDropdown";
import { FormulaNodeView } from "@/components/tiptap-template-editor/node-views/FormulaNodeView";
import { api } from "@/lib/api";
import { editorShortcutGroups } from "@/lib/editor-shortcuts";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual("@/lib/api");
  return {
    ...actual,
    api: {
      ...(actual as { api: object }).api,
      getFormulaFunctions: vi.fn().mockResolvedValue({ functions: [], categories: [] }),
      validateTemplate: vi.fn(),
      getTemplateVariables: vi.fn().mockResolvedValue({
        variables: {},
        max_lengths: {},
        colors: {},
        symbols: [],
        filters: [],
        formatting: {},
        syntax_examples: {},
      }),
    },
  };
});

function Wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

/** Row id → the test file proving its binding, which must say `binding: <id>`. */
const BINDING_PROOF: Record<string, string> = {
  undo: "page-builder-draw-mode.test.tsx",
  redo: "page-builder-draw-mode.test.tsx",
  applyFormula: "editor-shortcut-bindings.test.tsx",
  closePicker: "editor-shortcut-bindings.test.tsx",
  exitDrawMode: "page-builder-draw-mode.test.tsx",
};

describe("every listed shortcut has a binding test", () => {
  const listed = editorShortcutGroups((k) => k).flatMap((g) => g.items.map((i) => i.id));

  it("names a proof for exactly the listed rows", () => {
    expect(Object.keys(BINDING_PROOF).sort()).toEqual([...listed].sort());
  });

  it.each(Object.entries(BINDING_PROOF))("%s is proven in %s", (id, file) => {
    const source = readFileSync(path.resolve(__dirname, file), "utf8");
    expect(source).toContain(`binding: ${id}`);
  });
});

describe("Close a picker (Esc)", () => {
  // binding: closePicker
  it("closes a toolbar picker panel", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <ToolbarDropdown label="Colors" onClose={onClose}>
        <button type="button">Red</button>
      </ToolbarDropdown>,
    );
    await user.click(screen.getByRole("button", { name: "Colors" }));
    expect(screen.getByRole("dialog", { name: "Colors" })).toBeInTheDocument();
    fireEvent.keyDown(document.body, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Colors" })).toBeNull());
    expect(onClose).toHaveBeenCalled();
  });

  it("marks an open picker panel as an overlay the ? key leaves alone", async () => {
    const user = userEvent.setup();
    render(
      <ToolbarDropdown label="Colors">
        <button type="button">Red</button>
      </ToolbarDropdown>,
    );
    expect(document.querySelector("[data-editor-overlay]")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Colors" }));
    expect(screen.getByRole("dialog", { name: "Colors" })).toHaveAttribute("data-editor-overlay");
  });

  it("closes the formula modal, deleting a formula that was never given an expression", async () => {
    const deleteNode = vi.fn();
    const updateAttributes = vi.fn();
    const props = {
      node: { attrs: { expression: "", autoOpen: true } },
      updateAttributes,
      deleteNode,
    } as unknown as Parameters<typeof FormulaNodeView>[0];
    render(<FormulaNodeView {...props} />, { wrapper: Wrapper });
    // The panel inside is lazy-loaded; under load the first render can be slow.
    const dialog = await screen.findByRole("dialog", { name: "Formula editor" }, { timeout: 5000 });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    fireEvent.keyDown(document.body, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Formula editor" })).toBeNull(), {
      timeout: 5000,
    });
    expect(deleteNode).toHaveBeenCalled();
  });
});

describe("Apply a formula (Mod+Enter)", () => {
  // binding: applyFormula
  it("confirms a valid expression from the formula editor's keymap", async () => {
    vi.mocked(api.validateTemplate).mockResolvedValue({ valid: true, errors: [], warnings: [] } as never);
    const onConfirm = vi.fn();
    const { container } = render(<FormulaEditorPanel mode="edit" initialExpr="1 + 1" onConfirm={onConfirm} />, {
      wrapper: Wrapper,
    });
    const done = await screen.findByRole("button", { name: /Done/ }, { timeout: 5000 });
    await waitFor(() => expect(done).toBeEnabled(), { timeout: 3000 });
    const content = container.querySelector(".cm-content") as HTMLElement;
    fireEvent.keyDown(content, { key: "Enter", ctrlKey: true });
    expect(onConfirm).toHaveBeenCalledWith("1 + 1");
  });

  it("spells the Done button's chord from the registry with the kit Kbd", async () => {
    vi.mocked(api.validateTemplate).mockResolvedValue({ valid: true, errors: [], warnings: [] } as never);
    render(<FormulaEditorPanel mode="edit" initialExpr="1 + 1" onConfirm={vi.fn()} />, { wrapper: Wrapper });
    const done = await screen.findByRole("button", { name: /Done/ }, { timeout: 5000 });
    expect(done).toHaveAttribute("aria-keyshortcuts", "Control+Enter Meta+Enter");
    const caps = done.querySelector('kbd[aria-hidden="true"]');
    expect(caps?.textContent?.replace(/\s+/g, "")).toBe("CtrlEnter");
    expect(done.textContent).not.toContain("⌘↵");
  });
});
