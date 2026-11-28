/**
 * The template field's row model on its one paragraph of hardBreak-separated
 * rows: whether it is empty (the placeholder and the first-row caret, W-4),
 * and Enter as a fixed grid (W-4): a new row takes a blank one off the end.
 */
import type { Node as PMNode } from "@tiptap/pm/model";
import type { EditorState, Transaction } from "@tiptap/pm/state";

const CARET_ANCHOR = /​/g;

/** No text (caret anchors aside) and no chips: only blank rows. */
export function isEmptyTemplateDoc(doc: PMNode): boolean {
  let empty = true;
  doc.descendants((node) => {
    if (!empty) return false;
    if (node.isText) empty = (node.text ?? "").replace(CARET_ANCHOR, "") === "";
    else if (node.isInline && node.type.name !== "hardBreak") empty = false;
    return empty;
  });
  return empty;
}

/**
 * Enter: a hardBreak at the selection. When that makes more rows than the
 * board has and the last row is a blank one below the caret, the blank row
 * comes off the end, so typing down an empty or padded board never makes a
 * row past it (`7 > 6 rows` on the first Enter of a new page). Enter on the
 * last row still makes a row past the board (UX-3-4).
 */
export function enterTransaction(state: EditorState, boardLines: number): Transaction | null {
  const hardBreak = state.schema.nodes.hardBreak;
  if (!hardBreak) return null;
  const tr = state.tr.replaceSelectionWith(hardBreak.create());
  const paragraph = tr.doc.firstChild;
  if (!paragraph) return tr.scrollIntoView();
  const breaks: number[] = [];
  paragraph.forEach((child, offset) => {
    if (child.type === hardBreak) breaks.push(offset + 1);
  });
  const last = breaks[breaks.length - 1];
  if (breaks.length + 1 > boardLines && last !== undefined && last >= tr.selection.from) {
    const end = paragraph.content.size + 1;
    const tail = tr.doc.textBetween(last + 1, end, undefined, "￼").replace(CARET_ANCHOR, "");
    if (tail === "") tr.delete(last, end);
  }
  return tr.scrollIntoView();
}
