/**
 * TDD for Task 6: TipTapTemplateEditor imperative paint API.
 *
 * applyStroke() lets draw mode paint cells directly into the editor's
 * document without going through TipTap's normal text-input path. Each
 * stroke must land as ONE undo step (via closeHistory) so a drag gesture
 * doesn't produce dozens of undo entries, and undo must restore any dynamic
 * content (variables) that painting stripped from the line. The brush is a
 * DrawBrush (color, eraser, or stamp character), mapped to a cell via
 * brushToCell.
 */
import { render, waitFor } from "@testing-library/react";
import { Editor } from "@tiptap/core";
import { closeHistory } from "@tiptap/pm/history";
import StarterKit from "@tiptap/starter-kit";
import type { ComponentProps } from "react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  DrawHistoryEvent,
  TipTapTemplateEditorHandle,
} from "@/components/tiptap-template-editor/TipTapTemplateEditor";
import { TipTapTemplateEditor } from "@/components/tiptap-template-editor/TipTapTemplateEditor";
import type { CellPaint } from "@/components/tiptap-template-editor/utils/draw-mode";
import { parseTemplateSimple, serializeTemplateSimple } from "@/components/tiptap-template-editor/utils/serialization";
import { buildStrokeTransaction } from "@/components/tiptap-template-editor/utils/stroke-transaction";

type EditorProps = ComponentProps<typeof TipTapTemplateEditor>;

describe("TipTapTemplateEditor applyStroke", () => {
  async function setup(value: string, extraProps: Partial<EditorProps> = {}) {
    const ref = createRef<TipTapTemplateEditorHandle>();
    const onChange = vi.fn();
    const props: EditorProps = {
      value,
      onChange,
      showToolbar: false,
      boardLines: 6,
      boardWidth: 22,
      ...extraProps,
    };
    const { unmount, rerender } = render(<TipTapTemplateEditor ref={ref} {...props} />);
    await waitFor(() => expect(ref.current).not.toBeNull());
    return {
      ref,
      onChange,
      unmount,
      rerenderWithValue: (newValue: string) => rerender(<TipTapTemplateEditor ref={ref} {...props} value={newValue} />),
    };
  }

  it("paints cells into template lines as one change", async () => {
    const { ref, onChange } = await setup("HELLO\n\n\n\n\n");
    const rows = ref.current!.applyStroke(
      [
        { row: 0, col: 1 },
        { row: 2, col: 0 },
      ],
      { kind: "color", color: "blue" },
    );
    expect(rows).toEqual([0, 2]);
    await waitFor(() => {
      const last = onChange.mock.calls.at(-1)![0] as string;
      expect(last.split("\n")[0]).toBe("H{{blue}}LLO");
      expect(last.split("\n")[2]).toBe("{{blue}}");
    });
  });

  it("stamps a character with a char brush and undo restores the original", async () => {
    const { ref, onChange } = await setup("HELLO\n\n\n\n\n");
    ref.current!.applyStroke([{ row: 0, col: 1 }], { kind: "char", char: "A" });
    await waitFor(() => {
      expect((onChange.mock.calls.at(-1)![0] as string).split("\n")[0]).toBe("HALLO");
    });
    ref.current!.undo();
    await waitFor(() => {
      expect((onChange.mock.calls.at(-1)![0] as string).split("\n")[0]).toBe("HELLO");
    });
  });

  it("erases cells with the eraser brush", async () => {
    const { ref, onChange } = await setup("HELLO\n\n\n\n\n");
    ref.current!.applyStroke([{ row: 0, col: 4 }], { kind: "eraser" });
    await waitFor(() => {
      expect((onChange.mock.calls.at(-1)![0] as string).split("\n")[0]).toBe("HELL");
    });
  });

  it("strips variables on painted lines and undo restores them", async () => {
    const { ref, onChange } = await setup("HI {{weather.temp}}\n\n\n\n\n");
    ref.current!.applyStroke([{ row: 0, col: 0 }], { kind: "color", color: "red" });
    await waitFor(() => {
      expect((onChange.mock.calls.at(-1)![0] as string).split("\n")[0]).toBe("{{red}}I");
    });
    ref.current!.undo();
    await waitFor(() => {
      expect((onChange.mock.calls.at(-1)![0] as string).split("\n")[0]).toBe("HI {{weather.temp}}");
    });
  });

  it("two strokes are two undo steps", async () => {
    const { ref, onChange } = await setup("\n\n\n\n\n");
    ref.current!.applyStroke([{ row: 0, col: 0 }], { kind: "color", color: "red" });
    ref.current!.applyStroke([{ row: 0, col: 1 }], { kind: "color", color: "green" });
    ref.current!.undo();
    await waitFor(() => {
      expect((onChange.mock.calls.at(-1)![0] as string).split("\n")[0]).toBe("{{red}}");
    });
    ref.current!.undo();
    await waitFor(() => {
      expect((onChange.mock.calls.at(-1)![0] as string).split("\n")[0]).toBe("");
    });
  });

  it("undo/redo/applyStroke are safe no-ops once the editor is destroyed", async () => {
    const { ref, unmount } = await setup("HELLO\n\n\n\n\n");
    const handle = ref.current!;
    unmount();
    // TipTap's useEditor schedules the destroy after unmount — wait until the
    // guard actually sees a destroyed editor before asserting the no-ops.
    await waitFor(() => {
      expect(handle.applyStroke([{ row: 0, col: 0 }], { kind: "eraser" })).toEqual([]);
    });
    expect(() => handle.undo()).not.toThrow();
    expect(() => handle.redo()).not.toThrow();
  });
});

describe("TipTapTemplateEditor onDrawHistoryEvent", () => {
  async function setupWithEvents(value: string) {
    const events: DrawHistoryEvent[] = [];
    const ref = createRef<TipTapTemplateEditorHandle>();
    const onChange = vi.fn();
    const props: EditorProps = {
      value,
      onChange,
      showToolbar: false,
      boardLines: 6,
      boardWidth: 22,
      onDrawHistoryEvent: (e: DrawHistoryEvent) => events.push(e),
    };
    const { rerender } = render(<TipTapTemplateEditor ref={ref} {...props} />);
    await waitFor(() => expect(ref.current).not.toBeNull());
    return {
      ref,
      onChange,
      events,
      rerenderWithValue: (newValue: string) => rerender(<TipTapTemplateEditor ref={ref} {...props} value={newValue} />),
    };
  }

  async function lastLine0(onChange: ReturnType<typeof vi.fn>, expected: string) {
    await waitFor(() => {
      expect((onChange.mock.calls.at(-1)![0] as string).split("\n")[0]).toBe(expected);
    });
  }

  it("reports stroke boundaries when undoing and redoing a paint stroke", async () => {
    const { ref, onChange, events } = await setupWithEvents("HELLO\n\n\n\n\n");
    ref.current!.applyStroke([{ row: 0, col: 0 }], { kind: "color", color: "red" });
    await lastLine0(onChange, "{{red}}ELLO");
    expect(events).toEqual([]);

    ref.current!.undo();
    expect(events.at(-1)).toEqual({ action: "undo", stroke: true });
    await lastLine0(onChange, "HELLO");

    ref.current!.redo();
    expect(events.at(-1)).toEqual({ action: "redo", stroke: true });
    await lastLine0(onChange, "{{red}}ELLO");
  });

  it("reports stroke:false for non-stroke history steps interleaved with strokes", async () => {
    const { ref, onChange, events, rerenderWithValue } = await setupWithEvents("HELLO\n\n\n\n\n");
    ref.current!.applyStroke([{ row: 0, col: 0 }], { kind: "char", char: "X" });
    await lastLine0(onChange, "XELLO");

    // A non-stroke doc change: new value prop -> deferred setContent.
    rerenderWithValue("WORLD\n\n\n\n\n");
    await new Promise((resolve) => setTimeout(resolve, 20));

    ref.current!.undo(); // undoes the setContent
    expect(events.at(-1)).toEqual({ action: "undo", stroke: false });
    ref.current!.undo(); // undoes the stroke
    expect(events.at(-1)).toEqual({ action: "undo", stroke: true });
    await lastLine0(onChange, "HELLO");

    ref.current!.redo(); // re-applies the stroke
    expect(events.at(-1)).toEqual({ action: "redo", stroke: true });
    ref.current!.redo(); // re-applies the setContent
    expect(events.at(-1)).toEqual({ action: "redo", stroke: false });
  });
});

/**
 * Row-scoped stroke transactions: applyStroke must only replace the
 * hardBreak-delimited lines a stroke touched, keeping every other line's
 * nodes untouched (position/identity-stable) and preserving the caret. The
 * headless harness mirrors the component's applyStroke wrapper around
 * buildStrokeTransaction, using a char brush so the StarterKit-only schema
 * suffices.
 */
describe("buildStrokeTransaction (row-scoped strokes)", () => {
  let editor: Editor;

  function createHeadlessEditor(template: string, maxLines = 6): Editor {
    return new Editor({
      extensions: [
        StarterKit.configure({
          heading: false,
          blockquote: false,
          codeBlock: false,
          horizontalRule: false,
          bulletList: false,
          orderedList: false,
          listItem: false,
          code: false,
          bold: false,
          italic: false,
          strike: false,
        }),
      ],
      content: parseTemplateSimple(template, maxLines),
    });
  }

  function applyCharStroke(target: Editor, paints: Array<{ row: number; col: number }>, char = "X") {
    const lines = serializeTemplateSimple(target.getJSON(), 6).split("\n");
    const byRow = new Map<number, CellPaint[]>();
    for (const p of paints) {
      const arr = byRow.get(p.row) ?? [];
      arr.push({ col: p.col, cell: char });
      byRow.set(p.row, arr);
    }
    const tr = buildStrokeTransaction(target.state, lines, byRow, 22);
    expect(tr).not.toBeNull();
    target.view.dispatch(closeHistory(tr!));
  }

  function serializedLines(target: Editor): string[] {
    return serializeTemplateSimple(target.getJSON(), 6).split("\n");
  }

  afterEach(() => {
    editor?.destroy();
  });

  it("replaces only the painted row — untouched rows keep node identity", () => {
    editor = createHeadlessEditor("HELLO\nWORLD\n\n\n\n");
    // Row 0 is a single text node at pos 1 (TipTap merges the ZWS cursor
    // anchors with the line text on doc creation).
    const textBefore = editor.state.doc.nodeAt(1);
    expect(textBefore?.text).toBe("\u200BHELLO\u200B");

    applyCharStroke(editor, [{ row: 1, col: 0 }]);

    const lines = serializedLines(editor);
    expect(lines[0]).toBe("HELLO");
    expect(lines[1]).toBe("XORLD");
    // Structural sharing: a row-scoped replace must reuse row 0's node
    // object; a whole-doc rebuild would recreate it.
    expect(editor.state.doc.nodeAt(1)).toBe(textBefore);
  });

  it("preserves the caret when painting a different row", () => {
    editor = createHeadlessEditor("HELLO\nWORLD\n\n\n\n");
    editor.commands.setTextSelection(4); // inside "HELLO" on row 0
    const posBefore = editor.state.selection.from;

    applyCharStroke(editor, [{ row: 1, col: 2 }]);

    expect(editor.state.selection.from).toBe(posBefore);
    expect(editor.state.selection.empty).toBe(true);
  });

  it("keeps the selection valid when painting the caret's own row", () => {
    editor = createHeadlessEditor("HELLO\n\n\n\n\n");
    editor.commands.setTextSelection(4);

    applyCharStroke(editor, [{ row: 0, col: 1 }]);

    const { from, to } = editor.state.selection;
    expect(from).toBeGreaterThanOrEqual(0);
    expect(to).toBeLessThanOrEqual(editor.state.doc.content.size);
    expect(serializedLines(editor)[0]).toBe("HXLLO");
  });

  it("a multi-row stroke is still one undo step", () => {
    editor = createHeadlessEditor("\n\n\n\n\n");
    applyCharStroke(
      editor,
      [
        { row: 0, col: 0 },
        { row: 3, col: 2 },
      ],
      "A",
    );
    let lines = serializedLines(editor);
    expect(lines[0]).toBe("A");
    expect(lines[3]).toBe("  A");

    editor.commands.undo();
    lines = serializedLines(editor);
    expect(lines[0]).toBe("");
    expect(lines[3]).toBe("");
  });

  it("erasing a whole row keeps the line structure (hardBreak count) intact", () => {
    editor = createHeadlessEditor("A\nB\n\n\n\n");
    applyCharStroke(editor, [{ row: 1, col: 0 }], " ");

    const lines = serializedLines(editor);
    expect(lines[0]).toBe("A");
    expect(lines[1]).toBe("");
    let hardBreaks = 0;
    editor.state.doc.descendants((node) => {
      if (node.type.name === "hardBreak") hardBreaks++;
    });
    expect(hardBreaks).toBe(5);
  });

  it("painting below the last existing line appends the missing rows", () => {
    // Doc only has 2 lines (1 hardBreak); painting row 4 must extend it.
    editor = createHeadlessEditor("TOP", 2);
    applyCharStroke(editor, [{ row: 4, col: 1 }], "Z");

    const lines = serializedLines(editor);
    expect(lines[0]).toBe("TOP");
    expect(lines[4]).toBe(" Z");
  });
});
