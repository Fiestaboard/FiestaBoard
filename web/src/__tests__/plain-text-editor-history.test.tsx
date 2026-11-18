import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef, type RefObject, useState } from "react";
import { expect, it } from "vitest";

import { PlainTemplateToolbar } from "@/components/plain-template-toolbar";
import { PlainTextEditor, type PlainTextEditorHandle } from "@/components/plain-text-editor";

function ControlledEditor({
  initialValue,
  editorRef,
}: {
  initialValue: string;
  editorRef: RefObject<PlainTextEditorHandle | null>;
}) {
  const [value, setValue] = useState(initialValue);
  const [editorVersion, setEditorVersion] = useState(0);
  const [history, setHistory] = useState({ canUndo: false, canRedo: false });
  return (
    <>
      <label htmlFor="history-template">Template</label>
      <PlainTextEditor
        key={editorVersion}
        id="history-template"
        ref={editorRef}
        value={value}
        onChange={setValue}
        onHistoryChange={setHistory}
      />
      <PlainTemplateToolbar
        canUndo={history.canUndo}
        canRedo={history.canRedo}
        onUndo={() => editorRef.current?.undo()}
        onRedo={() => editorRef.current?.redo()}
        moreContent={null}
        onInsert={(text) => editorRef.current?.insert(text)}
      />
      <button onClick={() => setValue("External\nMiXeD")}>Replace document</button>
      <button onClick={() => setEditorVersion((version) => version + 1)}>Remount editor</button>
    </>
  );
}

function setup(initialValue: string) {
  const editorRef = createRef<PlainTextEditorHandle>();
  render(<ControlledEditor initialValue={initialValue} editorRef={editorRef} />);
  return {
    editorRef,
    input: screen.getByRole("textbox", { name: "Template" }) as HTMLTextAreaElement,
    undo: screen.getByRole("button", { name: "Undo" }),
    redo: screen.getByRole("button", { name: "Redo" }),
    user: userEvent.setup(),
  };
}

it("undoes and redoes literal variable insertion with its selected range and caret", async () => {
  const { editorRef, input, undo, redo, user } = setup("Ab\nHERE\nz");
  expect(undo).toBeDisabled();
  expect(redo).toBeDisabled();
  input.focus();
  input.setSelectionRange(3, 7);
  act(() => editorRef.current!.insert("{{weather.temperature}}"));
  expect(input).toHaveValue("Ab\n{{weather.temperature}}\nz");
  await waitFor(() => expect(input.selectionStart).toBe(26));
  await user.click(undo);
  expect(input).toHaveValue("Ab\nHERE\nz");
  await waitFor(() => expect([input.selectionStart, input.selectionEnd]).toEqual([3, 7]));
  await user.click(redo);
  expect(input).toHaveValue("Ab\n{{weather.temperature}}\nz");
  await waitFor(() => expect([input.selectionStart, input.selectionEnd]).toEqual([26, 26]));
  expect(input).toHaveFocus();
});

it("handles Mod+Z, Mod+Shift+Z and Mod+Y and clears redo after a new edit", async () => {
  const { input, undo, redo, user } = setup("MiX\n");
  await user.type(input, "ab");
  expect(input).toHaveValue("MiX\nab");
  await user.keyboard("{Control>}z{/Control}");
  expect(input).toHaveValue("MiX\na");
  await user.keyboard("{Control>}{Shift>}z{/Shift}{/Control}");
  expect(input).toHaveValue("MiX\nab");
  await user.keyboard("{Meta>}z{/Meta}");
  expect(input).toHaveValue("MiX\na");
  await user.keyboard("{Meta>}{Shift>}z{/Shift}{/Meta}");
  expect(input).toHaveValue("MiX\nab");
  await user.keyboard("{Control>}z{/Control}");
  await user.keyboard("{Control>}y{/Control}");
  expect(input).toHaveValue("MiX\nab");
  await user.keyboard("{Control>}z{/Control}");
  await user.type(input, "c");
  expect(input).toHaveValue("MiX\nac");
  expect(undo).toBeEnabled();
  expect(redo).toBeDisabled();
});

it("handles cancellable native beforeinput history requests through controlled history", async () => {
  const { editorRef, input } = setup("Ab");
  input.focus();
  input.setSelectionRange(2, 2);
  act(() => editorRef.current!.insert("X"));
  const undoEvent = new InputEvent("beforeinput", { inputType: "historyUndo", bubbles: true, cancelable: true });
  act(() => input.dispatchEvent(undoEvent));
  expect(undoEvent.defaultPrevented).toBe(true);
  expect(input).toHaveValue("Ab");
  const redoEvent = new InputEvent("beforeinput", { inputType: "historyRedo", bubbles: true, cancelable: true });
  act(() => input.dispatchEvent(redoEvent));
  expect(redoEvent.defaultPrevented).toBe(true);
  expect(input).toHaveValue("AbX");
});

it("applies a non-cancellable native history input once after the browser changes the value", async () => {
  const { editorRef, input, redo, user } = setup("Ab");
  input.focus();
  input.setSelectionRange(2, 2);
  act(() => editorRef.current!.insert("X"));
  await waitFor(() => expect(input.selectionStart).toBe(3));
  act(() => editorRef.current!.insert("Y"));
  const before = new InputEvent("beforeinput", { inputType: "historyUndo", bubbles: true, cancelable: false });
  act(() => input.dispatchEvent(before));
  expect(input).toHaveValue("AbXY");
  fireEvent.input(input, { target: { value: "AbX" }, inputType: "historyUndo" });
  expect(input).toHaveValue("AbX");
  await user.click(redo);
  expect(input).toHaveValue("AbXY");
  await waitFor(() => expect(input.selectionStart).toBe(4));
});

it("groups all IME candidate updates into one undoable edit", async () => {
  const { input, undo, redo, user } = setup("A");
  input.focus();
  input.setSelectionRange(1, 1);
  fireEvent.compositionStart(input);
  fireEvent.change(input, { target: { value: "Aに" } });
  fireEvent.change(input, { target: { value: "A日本" } });
  fireEvent.compositionEnd(input);
  expect(input).toHaveValue("A日本");
  await user.click(undo);
  expect(input).toHaveValue("A");
  expect(undo).toBeDisabled();
  expect(redo).toBeEnabled();
  await user.click(redo);
  expect(input).toHaveValue("A日本");
});

it("resets undo and redo when the controlled document is replaced externally", async () => {
  const { editorRef, input, undo, redo, user } = setup("Original");
  input.focus();
  input.setSelectionRange(8, 8);
  act(() => editorRef.current!.insert("!"));
  await user.click(undo);
  expect(redo).toBeEnabled();
  await user.click(screen.getByRole("button", { name: "Replace document" }));
  expect(input).toHaveValue("External\nMiXeD");
  expect(undo).toBeDisabled();
  expect(redo).toBeDisabled();
  await user.click(input);
  await user.keyboard("{Control>}z{/Control}");
  expect(input).toHaveValue("External\nMiXeD");
});

it("clears stale parent availability when an editor remounts with a fresh history", async () => {
  const { editorRef, input, undo, redo, user } = setup("A");
  input.focus();
  input.setSelectionRange(1, 1);
  act(() => editorRef.current!.insert("X"));
  expect(undo).toBeEnabled();
  await user.click(screen.getByRole("button", { name: "Remount editor" }));
  expect(screen.getByRole("textbox", { name: "Template" })).toHaveValue("AX");
  expect(undo).toBeDisabled();
  expect(redo).toBeDisabled();
});
