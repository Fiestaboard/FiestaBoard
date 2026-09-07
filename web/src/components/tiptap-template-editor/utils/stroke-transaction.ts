/**
 * Row-scoped ProseMirror transaction for draw-mode strokes.
 *
 * The editor keeps every board line inside a single paragraph, separated by
 * hardBreak nodes. A stroke only touches a handful of rows, so instead of
 * rebuilding the whole document (which rebuilds every node, drops the caret
 * and gives each stroke a whole-doc undo footprint) we compute the affected
 * hardBreak-delimited line ranges and replace just those. Untouched lines
 * keep their node objects (ProseMirror structural sharing), and the
 * selection maps through unchanged when it sits outside the painted rows.
 */

import type { Node as PMNode } from "@tiptap/pm/model";
import { Fragment } from "@tiptap/pm/model";
import type { EditorState, Transaction } from "@tiptap/pm/state";

import type { CellPaint } from "./draw-mode";
import { paintLine } from "./draw-mode";
import { parseLineContent } from "./serialization";

/** Cursor-anchor zero-width space, mirroring serialization.ts. */
const CURSOR_ANCHOR_CHAR = "\u200B";

export interface LineRange {
  /** Position of the line's first inline node (inside the paragraph). */
  from: number;
  /** Position just past the line's last inline node (before the trailing hardBreak). */
  to: number;
}

/**
 * Content ranges of each hardBreak-delimited line in the document's single
 * top-level paragraph.
 */
export function lineRanges(doc: PMNode): LineRange[] {
  const paragraph = doc.firstChild;
  if (!paragraph) return [];
  const ranges: LineRange[] = [];
  // The paragraph starts at doc position 0, so its content starts at 1.
  let lineStart = 1;
  paragraph.forEach((child, offset) => {
    if (child.type.name === "hardBreak") {
      const pos = 1 + offset;
      ranges.push({ from: lineStart, to: pos });
      lineStart = pos + child.nodeSize;
    }
  });
  ranges.push({ from: lineStart, to: 1 + paragraph.content.size });
  return ranges;
}

/**
 * Build a transaction that repaints only the rows a stroke touched.
 *
 * @param state      Current editor state.
 * @param lines      Current template lines (serialized doc, split on "\n").
 * @param byRow      Cell paints grouped by row index.
 * @param boardWidth Board columns, used to clamp painted lines.
 * @returns The transaction to dispatch (caller adds closeHistory), or null
 *          when there is nothing to paint.
 */
export function buildStrokeTransaction(
  state: EditorState,
  lines: string[],
  byRow: Map<number, CellPaint[]>,
  boardWidth: number,
): Transaction | null {
  if (byRow.size === 0) return null;
  const ranges = lineRanges(state.doc);
  if (ranges.length === 0) return null;

  const { schema } = state;
  const tr = state.tr;

  // Painting below the last existing line: extend the paragraph with empty
  // lines first. The insert happens at the old paragraph end, so the ranges
  // computed above (all strictly before it) stay valid.
  const maxRow = Math.max(...byRow.keys());
  if (maxRow >= ranges.length) {
    const end = ranges[ranges.length - 1].to;
    const appended: PMNode[] = [];
    let pos = end;
    for (let i = ranges.length; i <= maxRow; i++) {
      appended.push(schema.nodes.hardBreak.create(), schema.text(CURSOR_ANCHOR_CHAR));
      pos += 1; // hardBreak
      ranges.push({ from: pos, to: pos + 1 }); // the cursor-anchor text node
      pos += 1;
    }
    tr.insert(end, appended);
  }

  // Replace affected rows bottom-up so the untouched ranges above each
  // replacement keep their original positions.
  const rows = [...byRow.keys()].sort((a, b) => b - a);
  for (const row of rows) {
    const painted = paintLine(lines[row] ?? "", byRow.get(row)!, boardWidth);
    // Mirror parseTemplateSimple's line shape: leading + trailing cursor anchors.
    const content = [
      { type: "text", text: CURSOR_ANCHOR_CHAR },
      ...parseLineContent(painted),
      { type: "text", text: CURSOR_ANCHOR_CHAR },
    ];
    const { from, to } = ranges[row];
    tr.replaceWith(from, to, Fragment.fromJSON(schema, content));
  }

  return tr;
}
