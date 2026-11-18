import { afterEach, describe, expect, it, vi } from "vitest";

import { measureBoardViewport } from "@/hooks/use-board-viewport-scroll";
import { focusTemplateCell, measureLineBoxes } from "@/lib/complex-editing-dom";

function rect(left: number, top: number, width: number, height: number): DOMRect {
  return { left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON: () => ({}) };
}

function richEditor(lines: string[]) {
  const root = document.createElement("div");
  const editable = document.createElement("div");
  editable.setAttribute("contenteditable", "true");
  editable.className = "ProseMirror";
  const p = document.createElement("p");
  lines.forEach((line, i) => {
    if (line) p.append(document.createTextNode(line));
    if (i < lines.length - 1) p.append(document.createElement("br"));
  });
  editable.append(p);
  root.append(editable);
  document.body.append(root);
  return { root, editable, p };
}

afterEach(() => {
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

describe("focusTemplateCell", () => {
  it("places the caret at a row and column of the rich editor", () => {
    const { root, editable, p } = richEditor(["HEADER", "TONIGHT AT ROSA'S"]);
    expect(focusTemplateCell(root, 2, 9)).toBe(true);
    expect(document.activeElement).toBe(editable);
    const range = window.getSelection()!.getRangeAt(0);
    expect(range.startContainer).toBe(p.childNodes[2]);
    expect(range.startOffset).toBe(8);
  });

  it("counts an atom as one column", () => {
    const { root, p } = richEditor(["", ""]);
    const atom = document.createElement("span");
    atom.setAttribute("contenteditable", "false");
    atom.textContent = "weather.temp";
    p.insertBefore(atom, p.firstChild);
    p.insertBefore(document.createTextNode("°F"), atom.nextSibling);
    expect(focusTemplateCell(root, 1, 3)).toBe(true);
    const range = window.getSelection()!.getRangeAt(0);
    expect(range.startContainer.textContent).toBe("°F");
    expect(range.startOffset).toBe(1);
  });

  it("refuses a row past the template", () => {
    const { root } = richEditor(["ONE"]);
    expect(focusTemplateCell(root, 3, 1)).toBe(false);
    expect(focusTemplateCell(document.createElement("div"), 1, 1)).toBe(false);
  });

  it("moves the plain textarea's selection", () => {
    const root = document.createElement("div");
    const textarea = document.createElement("textarea");
    textarea.value = "AB\nCDEF\nG";
    root.append(textarea);
    document.body.append(root);
    expect(focusTemplateCell(root, 2, 3)).toBe(true);
    expect(textarea.selectionStart).toBe(5);
    expect(focusTemplateCell(root, 3, 40)).toBe(true);
    expect(textarea.selectionStart).toBe(9);
    expect(focusTemplateCell(root, 9, 1)).toBe(false);
  });
});

describe("measureLineBoxes", () => {
  it("falls back to even rows when there is no layout", () => {
    const { root } = richEditor(["A", "B", "C"]);
    const none = () => rect(0, 0, 0, 0);
    vi.spyOn(Range.prototype, "getBoundingClientRect").mockImplementation(none);
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(none);
    const boxes = measureLineBoxes(root, root, 3);
    expect(boxes.map((b) => b.top)).toEqual([0, 24, 48]);
  });

  it("uses the measured range of each line", () => {
    const { root } = richEditor(["A", "B"]);
    vi.spyOn(root, "getBoundingClientRect").mockReturnValue(rect(0, 100, 300, 60));
    const tops = [110, 140];
    let call = 0;
    vi.spyOn(document, "createRange").mockImplementation(() => {
      const range = new Range();
      const top = tops[call++ % 2];
      range.getBoundingClientRect = () => rect(0, top, 10, 20);
      return range;
    });
    expect(measureLineBoxes(root, root, 2)).toEqual([
      { top: 10, height: 20 },
      { top: 40, height: 20 },
    ]);
  });

  it("has a fixed row grid without an editor", () => {
    expect(measureLineBoxes(document.createElement("div"), document.body, 2)).toEqual([
      { top: 0, height: 24 },
      { top: 24, height: 24 },
    ]);
  });
});

describe("measureBoardViewport", () => {
  function board(columns: number, pitch: number, scrollLeft: number) {
    const stage = document.createElement("div");
    const scroller = document.createElement("div");
    scroller.setAttribute("data-slot", "board-viewport-scroller");
    stage.append(scroller);
    for (let row = 0; row < 2; row++) {
      for (let col = 0; col < columns; col++) {
        const t = document.createElement("div");
        t.dataset.row = String(row);
        t.dataset.col = String(col);
        const seam = col >= 15 ? 6 : 0;
        t.getBoundingClientRect = () => rect(20 + col * pitch + seam - scrollLeft, 30 + row * 20, pitch - 2, 18);
        scroller.append(t);
      }
    }
    stage.getBoundingClientRect = () => rect(0, 0, 400, 200);
    scroller.getBoundingClientRect = () => rect(10, 20, 200, 160);
    return stage;
  }

  it("reports the visible columns and tile geometry", () => {
    const geometry = measureBoardViewport(board(30, 15, 0), 30);
    expect(geometry.pitch).toBe(15);
    expect(geometry.first).toBe(1);
    expect(geometry.last).toBe(12);
    expect(geometry.tileWidth).toBe(13);
    expect(geometry.columnGap).toBe(2);
    expect(geometry.rowGap).toBe(2);
    expect(geometry.seamGap).toBe(6);
    expect(geometry.originX).toBe(20);
    expect(geometry.clip).toEqual({ x: 10, y: 20, width: 200, height: 160 });
  });

  it("follows the scroll", () => {
    const geometry = measureBoardViewport(board(30, 15, 150), 30);
    expect(geometry.first).toBe(11);
  });

  it("shows the whole board before tiles render", () => {
    const stage = document.createElement("div");
    expect(measureBoardViewport(stage, 96)).toMatchObject({ first: 1, last: 96, pitch: 0, clip: null });
  });
});
