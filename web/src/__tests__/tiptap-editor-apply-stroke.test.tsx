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
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";

import type { TipTapTemplateEditorHandle } from "@/components/tiptap-template-editor/TipTapTemplateEditor";
import { TipTapTemplateEditor } from "@/components/tiptap-template-editor/TipTapTemplateEditor";

describe("TipTapTemplateEditor applyStroke", () => {
  async function setup(value: string) {
    const ref = createRef<TipTapTemplateEditorHandle>();
    const onChange = vi.fn();
    render(
      <TipTapTemplateEditor
        ref={ref}
        value={value}
        onChange={onChange}
        showToolbar={false}
        boardLines={6}
        boardWidth={22}
      />,
    );
    await waitFor(() => expect(ref.current).not.toBeNull());
    return { ref, onChange };
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
});
