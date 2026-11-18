/**
 * DOM helpers for the 2.9 complex-editing tools that work against the
 * editor's existing template surfaces (the TipTap rich editor, whose lines
 * are `<br>`-separated runs inside one paragraph, and the plain textarea)
 * without changing either editor.
 */

const ZWS = "​";

export interface LineBox {
  top: number;
  height: number;
}

function richParagraph(root: Element): HTMLElement | null {
  return (
    root.querySelector<HTMLElement>('[contenteditable="true"] p') ?? root.querySelector<HTMLElement>(".ProseMirror p")
  );
}

function lineBreaks(paragraph: Element): HTMLBRElement[] {
  return Array.from(paragraph.children).filter((child): child is HTMLBRElement => child.tagName === "BR");
}

/**
 * The vertical box of each template line in the rich editor, relative to
 * `container`. A line's box is its content's range; an empty line falls back
 * to its `<br>`, and an unmeasurable layout (no layout engine) to an even
 * split of the paragraph or a fixed 24 px row.
 */
export function measureLineBoxes(root: Element, container: Element, count: number): LineBox[] {
  const paragraph = richParagraph(root);
  const origin = container.getBoundingClientRect().top;
  if (!paragraph) return Array.from({ length: count }, (_, i) => ({ top: i * 24, height: 24 }));
  const breaks = lineBreaks(paragraph);
  const whole = paragraph.getBoundingClientRect();
  const even = whole.height > 0 ? whole.height / Math.max(1, Math.max(count, breaks.length)) : 24;
  return Array.from({ length: count }, (_, i) => {
    const range = document.createRange();
    if (i === 0) range.setStart(paragraph, 0);
    else if (breaks[i - 1]) range.setStartAfter(breaks[i - 1]);
    else return { top: whole.top - origin + i * even, height: even };
    if (breaks[i]) range.setEndBefore(breaks[i]);
    else range.setEnd(paragraph, paragraph.childNodes.length);
    let rect = typeof range.getBoundingClientRect === "function" ? range.getBoundingClientRect() : null;
    if (!(rect && rect.height > 0) && breaks[i]) {
      const brRange = document.createRange();
      brRange.selectNode(breaks[i]);
      rect = typeof brRange.getBoundingClientRect === "function" ? brRange.getBoundingClientRect() : null;
    }
    if (!(rect && rect.height > 0)) return { top: whole.top - origin + i * even, height: even };
    return { top: rect.top - origin, height: rect.height };
  });
}

/**
 * Put the caret at a one-based row and column of the template, in whichever
 * editor is mounted under `root`, and focus it. Atoms (variables, formulas,
 * colour tiles) count as one column, as the caret steps over them. Returns
 * false when there is no editor or no such row.
 */
export function focusTemplateCell(root: Element, row: number, column: number): boolean {
  const textarea = root.querySelector("textarea");
  if (textarea) {
    const lines = textarea.value.split("\n");
    if (row < 1 || row > Math.max(1, lines.length)) return false;
    let offset = 0;
    for (let i = 0; i < row - 1; i++) offset += lines[i].length + 1;
    offset += Math.min(Math.max(0, column - 1), (lines[row - 1] ?? "").length);
    textarea.focus();
    textarea.setSelectionRange(offset, offset);
    return true;
  }
  const editable = root.querySelector<HTMLElement>('[contenteditable="true"]');
  const paragraph = richParagraph(root);
  if (!editable || !paragraph) return false;
  const breaks = lineBreaks(paragraph);
  if (row < 1 || row > breaks.length + 1) return false;
  const nodes = Array.from(paragraph.childNodes);
  let index = row === 1 ? 0 : nodes.indexOf(breaks[row - 2]) + 1;
  let remaining = Math.max(0, column - 1);
  let target: { node: Node; offset: number } = { node: paragraph, offset: index };
  while (index < nodes.length && nodes[index].nodeName !== "BR") {
    const node = nodes[index];
    if (node.nodeType === Node.TEXT_NODE) {
      const text = node.textContent ?? "";
      let offset = 0;
      while (offset < text.length && (remaining > 0 || text[offset] === ZWS)) {
        if (text[offset] !== ZWS) remaining--;
        offset++;
      }
      target = { node, offset };
      if (remaining === 0) break;
    } else {
      if (remaining === 0) break;
      remaining--;
      target = { node: paragraph, offset: index + 1 };
    }
    index++;
  }
  editable.focus();
  const selection = window.getSelection();
  if (!selection) return true;
  const range = document.createRange();
  range.setStart(target.node, target.offset);
  range.collapse(true);
  selection.removeAllRanges();
  selection.addRange(range);
  return true;
}
