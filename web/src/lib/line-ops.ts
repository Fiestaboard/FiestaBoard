// Pure helpers for applying AI line-level operations to template/
// alignment/wrap arrays. Shared between the editor (which applies
// them as the source of truth) and the AI chat panel (which uses
// them to compute "what would the board look like after this patch?"
// so it can render an inline preview without round-tripping the
// editor.

import type { LineOp } from "./ai-chat-types";
import type { LineAlignment, LineMetadata } from "./api";

/**
 * Apply one line-level op in place. Out-of-range indices are clamped
 * so a misbehaving model can't crash the caller — we'd rather keep
 * the editor session alive and surface a warning in the chat panel.
 */
export function applyLineOpInPlace(
  op: LineOp,
  template: string[],
  alignments: LineAlignment[],
  wraps: boolean[],
): void {
  switch (op.type) {
    case "replace_line": {
      if (op.index < 0 || op.index >= template.length) return;
      template[op.index] = op.text;
      if (op.alignment) alignments[op.index] = op.alignment;
      if (op.wrap !== undefined) wraps[op.index] = op.wrap;
      return;
    }
    case "insert_line": {
      const idx = Math.max(0, Math.min(op.index, template.length));
      template.splice(idx, 0, op.text);
      alignments.splice(idx, 0, op.alignment ?? "left");
      wraps.splice(idx, 0, op.wrap ?? false);
      return;
    }
    case "delete_line": {
      if (op.index < 0 || op.index >= template.length) return;
      template.splice(op.index, 1);
      alignments.splice(op.index, 1);
      wraps.splice(op.index, 1);
      return;
    }
    case "update_line_metadata": {
      if (op.index < 0 || op.index >= template.length) return;
      if (op.alignment) alignments[op.index] = op.alignment;
      if (op.wrap !== undefined) wraps[op.index] = op.wrap;
      return;
    }
  }
}

/**
 * Apply an entire patch (sequence of ops) to a snapshot and return
 * the resulting template + line_metadata. Pure — does not mutate the
 * input arrays. Used by the chat panel to render "post-patch" board
 * previews inline with assistant tool-call cards.
 */
export function applyPatchToSnapshot(
  changes: LineOp[],
  template: string[],
  lineMetadata: LineMetadata[],
): { template: string[]; line_metadata: LineMetadata[] } {
  const nextTemplate = template.slice();
  const nextAlign: LineAlignment[] = lineMetadata.map((m) => (m.alignment as LineAlignment) ?? "left");
  const nextWrap: boolean[] = lineMetadata.map((m) => Boolean(m.wrap));
  for (const change of changes) {
    applyLineOpInPlace(change, nextTemplate, nextAlign, nextWrap);
  }
  return {
    template: nextTemplate,
    line_metadata: nextTemplate.map((_, i) => ({
      alignment: nextAlign[i] ?? "left",
      wrap: nextWrap[i] ?? false,
    })),
  };
}
