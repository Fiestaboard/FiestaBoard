import type { TemplateEditorToolbarProps } from "@fiestaboard/ui";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { EditorTabletTools } from "@/components/editor-tablet-tools";

function commandEditor() {
  const chain = {
    focus: vi.fn(() => chain),
    undo: vi.fn(() => chain),
    redo: vi.fn(() => chain),
    insertContent: vi.fn(() => chain),
    toggleMark: vi.fn(() => chain),
    deleteSelection: vi.fn(() => chain),
    run: vi.fn(),
  };
  const listeners = new Map<string, () => void>();
  const editor = {
    chain: () => chain,
    can: () => ({ undo: () => true, redo: () => true }),
    state: { selection: { from: 0, to: 3 }, doc: { textBetween: vi.fn(() => "CUT ME") } },
    commands: { setTextSelection: vi.fn() },
    view: { focus: vi.fn() },
    on: (event: string, callback: () => void) => listeners.set(event, callback),
    off: (event: string) => listeners.delete(event),
  };
  return { editor: editor as unknown as TemplateEditorToolbarProps["editor"], chain, raw: editor, listeners };
}

describe("EditorTabletTools", () => {
  it("keeps the dock above the visual viewport keyboard as its size changes", () => {
    const viewport = Object.assign(new EventTarget(), { height: window.innerHeight - 200, offsetTop: 10 });
    vi.stubGlobal("visualViewport", viewport);
    const { unmount } = render(<EditorTabletTools editor={null} />);
    try {
      const toolbar = screen.getByRole("group", { name: "Editor tools" });
      expect(toolbar).toHaveStyle({ bottom: "190px" });
      act(() => {
        viewport.height = window.innerHeight - 350;
        viewport.dispatchEvent(new Event("resize"));
      });
      expect(toolbar).toHaveStyle({ bottom: "340px" });
    } finally {
      unmount();
      vi.unstubAllGlobals();
    }
  });

  it("keeps touch tools with anchored pickers instead of sheets", async () => {
    const user = userEvent.setup();
    render(<EditorTabletTools editor={null} templateVariables={{ variables: {}, colors: { red: 63 } }} />);
    const toolbar = screen.getByRole("group", { name: "Editor tools" });
    expect(toolbar).toHaveAttribute("data-size", "touch");
    await user.click(screen.getByRole("button", { name: "Colors" }));
    expect(screen.getByRole("button", { name: "Colors" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("listbox", { name: "Color picker" })).toBeVisible();
    expect(document.querySelector('[data-slot="sheet-content"]')).toBeNull();
  });

  it("preserves host More content, alignment and wrap callbacks", async () => {
    const user = userEvent.setup();
    const onAlignmentChange = vi.fn();
    const onWrapToggle = vi.fn();
    render(
      <EditorTabletTools
        editor={null}
        onAlignmentChange={onAlignmentChange}
        onWrapToggle={onWrapToggle}
        moreContent={<span>Mirror host slot</span>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Formatting" }));
    await user.click(screen.getByRole("radio", { name: "Center" }));
    expect(onAlignmentChange).toHaveBeenCalledWith("center");
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "More" }));
    expect(screen.getByText("Mirror host slot")).toBeVisible();
    await user.click(screen.getByRole("switch", { name: "Wrap this line" }));
    expect(onWrapToggle).toHaveBeenCalledOnce();
  });

  it("uses LED tools and closes the host size picker", async () => {
    const user = userEvent.setup();
    render(
      <EditorTabletTools
        editor={null}
        capabilities="led-text"
        renderSizePicker={({ close }) => <button onClick={close}>Choose size</button>}
      />,
    );
    expect(screen.getByRole("button", { name: "Text color" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Icon" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Formatting" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Size" }));
    await user.click(screen.getByRole("button", { name: "Choose size" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("dispatches undo and formula through the editor and draw Done through the host", async () => {
    const run = vi.fn();
    const chain = {
      focus: vi.fn(() => chain),
      undo: vi.fn(() => chain),
      redo: vi.fn(() => chain),
      insertContent: vi.fn(() => chain),
      run,
    };
    const editor = {
      can: () => ({ undo: () => true, redo: () => false }),
      chain: () => chain,
      state: { selection: { from: 0, to: 0 } },
      on: vi.fn(),
      off: vi.fn(),
    } as unknown as TemplateEditorToolbarProps["editor"];
    const user = userEvent.setup();
    const done = vi.fn();
    const { rerender } = render(<EditorTabletTools editor={editor} onDrawModeToggle={done} />);
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(chain.undo).toHaveBeenCalledOnce();
    await user.click(screen.getByRole("button", { name: "Formula" }));
    expect(chain.insertContent).toHaveBeenCalledWith({ type: "formula", attrs: { expression: "", autoOpen: true } });
    rerender(<EditorTabletTools editor={editor} drawMode onDrawModeToggle={done} />);
    expect(screen.getByRole("button", { name: "Brush" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Done" }));
    expect(done).toHaveBeenCalledOnce();
  });

  it("inserts host variables and formatting through the real parser, closing their pickers", async () => {
    const user = userEvent.setup();
    const { editor, chain } = commandEditor();
    render(
      <EditorTabletTools
        editor={editor}
        templateVariables={{
          variables: { weather: ["temperature"] },
          formatting: { center: { syntax: "{{center}}", description: "Center line" } },
        }}
        renderVariablePicker={({ onInsert }) => (
          <button onClick={() => onInsert("{{weather.temperature}}")}>Temperature</button>
        )}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Variables" }));
    await user.click(screen.getByRole("button", { name: "Temperature" }));
    expect(chain.insertContent).toHaveBeenCalledWith(
      expect.arrayContaining([
        expect.objectContaining({
          type: "variable",
          attrs: expect.objectContaining({ pluginId: "weather", field: "temperature" }),
        }),
      ]),
    );
    expect(screen.queryByText("Temperature")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Formatting" }));
    await user.click(screen.getByText("center", { exact: true }));
    expect(chain.insertContent).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("button", { name: "Formatting" })).toHaveAttribute("aria-expanded", "false");
  });

  it("copies and cuts selected content, pastes clipboard markup and dispatches redo", async () => {
    const user = userEvent.setup();
    const write = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    const read = vi.spyOn(navigator.clipboard, "readText").mockResolvedValue("{{weather.temperature}}");
    const { editor, chain, raw, listeners } = commandEditor();
    const { unmount } = render(<EditorTabletTools editor={editor} />);
    await user.click(screen.getByRole("button", { name: "Redo" }));
    expect(chain.redo).toHaveBeenCalledOnce();
    await user.click(screen.getByRole("button", { name: "More" }));
    await user.click(screen.getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(write).toHaveBeenCalledWith("CUT ME"));
    expect(chain.deleteSelection).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Cut" }));
    await waitFor(() => expect(chain.deleteSelection).toHaveBeenCalledOnce());
    await user.click(screen.getByRole("button", { name: "Paste" }));
    await waitFor(() =>
      expect(chain.insertContent).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.objectContaining({
            type: "variable",
            attrs: expect.objectContaining({ pluginId: "weather", field: "temperature" }),
          }),
        ]),
      ),
    );
    expect(raw.view.focus).toHaveBeenCalledTimes(3);
    read.mockResolvedValue("");
    await user.click(screen.getByRole("button", { name: "Paste" }));
    expect(chain.insertContent).toHaveBeenCalledOnce();
    act(() => {
      raw.state.selection.to = 0;
      listeners.get("selectionUpdate")?.();
    });
    expect(screen.getByRole("button", { name: "Cut" })).toBeDisabled();
    unmount();
    expect(listeners.size).toBe(0);
  });

  it("uses the browser clipboard fallback when permission is denied", async () => {
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));
    const exec = vi.fn();
    Object.defineProperty(document, "execCommand", { configurable: true, value: exec });
    const { editor, chain } = commandEditor();
    render(<EditorTabletTools editor={editor} />);
    await user.click(screen.getByRole("button", { name: "More" }));
    await user.click(screen.getByRole("button", { name: "Cut" }));
    await waitFor(() => expect(exec).toHaveBeenCalledWith("cut"));
    expect(chain.deleteSelection).not.toHaveBeenCalled();
  });

  it("applies LED text and block colors and inserts icons with extended markup", async () => {
    const user = userEvent.setup();
    const { editor, chain } = commandEditor();
    render(<EditorTabletTools editor={editor} charset="led_3x5" />);
    await user.click(screen.getByRole("button", { name: "Text color" }));
    fireEvent.click(document.querySelector('[data-text-color="red"]')!);
    expect(chain.toggleMark).toHaveBeenCalledWith("colorSpan", { color: "red", background: null });
    await user.click(screen.getByRole("button", { name: "Text color" }));
    fireEvent.click(document.querySelector('[data-block-color="white"]')!);
    expect(chain.toggleMark).toHaveBeenCalledWith("colorSpan", { color: "black", background: "white" });
    await user.click(screen.getByRole("button", { name: "Icon" }));
    const icon = document.querySelector<HTMLButtonElement>('[data-icon="sun"]')!;
    fireEvent.click(icon);
    expect(chain.insertContent).toHaveBeenCalledWith(
      expect.arrayContaining([
        expect.objectContaining({ type: "icon", attrs: expect.objectContaining({ name: "sun" }) }),
      ]),
    );
    expect(screen.getByRole("button", { name: "Icon" })).toHaveAttribute("aria-expanded", "false");
  });

  it("inserts a split-flap color tile and selects draw colors, eraser and stamps", async () => {
    const user = userEvent.setup();
    const { editor, chain } = commandEditor();
    const brush = vi.fn();
    const draw = vi.fn();
    const { rerender } = render(
      <EditorTabletTools editor={editor} templateVariables={{ variables: {}, colors: { red: 63 } }} />,
    );
    await user.click(screen.getByRole("button", { name: "Colors" }));
    await user.click(screen.getByRole("option", { name: "Red color" }));
    expect(chain.insertContent).toHaveBeenCalledWith(
      expect.arrayContaining([
        expect.objectContaining({ type: "colorTile", attrs: expect.objectContaining({ color: "red" }) }),
      ]),
    );
    rerender(<EditorTabletTools editor={editor} drawMode onDrawBrushChange={brush} onDrawModeToggle={draw} />);
    await user.click(screen.getByRole("button", { name: "Brush" }));
    await user.click(screen.getByRole("button", { name: "Blue" }));
    expect(brush).toHaveBeenLastCalledWith({ kind: "color", color: "blue" });
    await user.click(screen.getByRole("button", { name: "Brush" }));
    await user.click(screen.getByRole("button", { name: "Eraser" }));
    expect(brush).toHaveBeenLastCalledWith({ kind: "eraser" });
    await user.click(screen.getByRole("button", { name: "Brush" }));
    fireEvent.click(document.querySelector('[data-draw-char="A"]')!);
    expect(brush).toHaveBeenLastCalledWith({ kind: "char", char: "A" });
    await user.click(screen.getByRole("button", { name: "Done" }));
    expect(draw).toHaveBeenCalledOnce();
  });

  it("invokes More draw/sync and the host entity picker with deferred insertion", async () => {
    const user = userEvent.setup();
    const { editor, chain } = commandEditor();
    const draw = vi.fn();
    const sync = vi.fn();
    render(
      <EditorTabletTools
        editor={editor}
        onDrawModeToggle={draw}
        onSyncFromBoard={sync}
        templateVariables={{ variables: { home_assistant: ["sensor.state"] } }}
        entityPickerSlot={({ open, onSelect, onClose }) =>
          open ? (
            <>
              <button onClick={() => onSelect("{{home_assistant.sensor.state}}")}>Select sensor</button>
              <button onClick={onClose}>Close entities</button>
            </>
          ) : null
        }
      />,
    );
    await user.click(screen.getByRole("button", { name: "More" }));
    await user.click(screen.getByRole("button", { name: "Draw on board" }));
    expect(draw).toHaveBeenCalledOnce();
    await user.click(screen.getByRole("button", { name: "More" }));
    await user.click(screen.getByRole("button", { name: "Sync from current board display" }));
    expect(sync).toHaveBeenCalledOnce();
    await user.click(screen.getByRole("button", { name: "Home Assistant entities" }));
    await user.click(screen.getByRole("button", { name: "Select sensor" }));
    await waitFor(() =>
      expect(chain.insertContent).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.objectContaining({
            type: "variable",
            attrs: expect.objectContaining({ pluginId: "home_assistant", field: "sensor.state" }),
          }),
        ]),
      ),
    );
    await user.click(screen.getByRole("button", { name: "Close entities" }));
    expect(screen.queryByText("Select sensor")).toBeNull();
  });
});
