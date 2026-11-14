import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef } from "react";
import { describe, expect, it } from "vitest";

import { EditorShortcutList, useEditorShortcutList } from "@/components/editor-shortcut-list";

function Harness({ boardViewport = false }: { boardViewport?: boolean }) {
  const shortcuts = useEditorShortcutList();
  const templateRef = useRef<HTMLDivElement>(null);
  return (
    <div>
      <EditorShortcutList variant="header" state={shortcuts} anchorRef={templateRef} boardViewport={boardViewport} />
      <EditorShortcutList variant="hint" state={shortcuts} anchorRef={templateRef} boardViewport={boardViewport} />
      <input aria-label="Page name" />
      <textarea aria-label="Plain text" />
      <div aria-label="Template" contentEditable suppressContentEditableWarning role="textbox" />
      <div ref={templateRef} data-testid="template-column" />
      <div role="alertdialog" aria-label="Delete page">
        <button type="button">Cancel</button>
      </div>
    </div>
  );
}

const dialog = () => screen.queryByRole("dialog", { name: "Keyboard shortcuts" });

describe("EditorShortcutList", () => {
  it("opens the list when ? is pressed outside a text field", async () => {
    render(<Harness />);
    expect(dialog()).toBeNull();
    fireEvent.keyDown(document.body, { key: "?", shiftKey: true });
    expect(await screen.findByRole("dialog", { name: "Keyboard shortcuts" })).toBeInTheDocument();
  });

  it.each([
    ["the page name input", "Page name"],
    ["the plain-text textarea", "Plain text"],
    ["the contenteditable template", "Template"],
  ])("leaves ? as a typed character in %s", async (_where, label) => {
    render(<Harness />);
    const field = screen.getByLabelText(label);
    const event = fireEvent.keyDown(field, { key: "?", shiftKey: true });
    expect(event).toBe(true); // not prevented
    await new Promise((r) => setTimeout(r, 20));
    expect(dialog()).toBeNull();
  });

  it("ignores ? inside another open dialog, with an accelerator, or once already handled", async () => {
    render(<Harness />);
    fireEvent.keyDown(screen.getByRole("button", { name: "Cancel" }), { key: "?", shiftKey: true });
    fireEvent.keyDown(document.body, { key: "?", metaKey: true });
    const handled = new KeyboardEvent("keydown", { key: "?", bubbles: true, cancelable: true });
    handled.preventDefault();
    document.body.dispatchEvent(handled);
    await new Promise((r) => setTimeout(r, 20));
    expect(dialog()).toBeNull();
  });

  it("lists exactly the registry's bound editor shortcuts", async () => {
    render(<Harness />);
    fireEvent.keyDown(document.body, { key: "?" });
    const list = await screen.findByRole("dialog", { name: "Keyboard shortcuts" });
    const terms = within(list)
      .getAllByRole("term")
      .map((dt) => dt.textContent);
    expect(terms).toEqual(["Undo", "Redo", "Apply a formula (formula editor)", "Close a picker", "Leave draw mode"]);
    expect(within(list).getByText(/No single-key shortcuts while typing/)).toBeInTheDocument();
  });

  it("adds the preview's own keys only when the preview is a BoardViewport", async () => {
    render(<Harness boardViewport />);
    fireEvent.keyDown(document.body, { key: "?" });
    const list = await screen.findByRole("dialog", { name: "Keyboard shortcuts" });
    expect(within(list).getByText("Scroll the preview by one note")).toBeInTheDocument();
    expect(within(list).getByText("Fit / Actual size (preview focused)")).toBeInTheDocument();
  });

  it("opens from the header Shortcuts button, which advertises ?", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const button = screen.getByRole("button", { name: "Shortcuts" });
    expect(button).toHaveAttribute("aria-keyshortcuts", "?");
    await user.click(button);
    expect(await screen.findByRole("dialog", { name: "Keyboard shortcuts" })).toBeInTheDocument();
  });

  it("opens from the toolbar hint, and only one list is open at a time", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: /All shortcuts/ }));
    await screen.findByRole("dialog", { name: "Keyboard shortcuts" });
    fireEvent.keyDown(document.body, { key: "?" });
    await waitFor(() => expect(screen.getAllByRole("dialog", { name: "Keyboard shortcuts" })).toHaveLength(1));
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    fireEvent.keyDown(document.body, { key: "?" });
    await screen.findByRole("dialog", { name: "Keyboard shortcuts" });
    await user.keyboard("{Escape}");
    await waitFor(() => expect(dialog()).toBeNull());
  });
});
