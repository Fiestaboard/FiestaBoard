/**
 * "Jump to source" for the Problems console: put the caret at the start of a
 * template line in whichever editor surface is mounted, without a new handle
 * on the page builder (2.9/2.10 own its internals).
 *
 * The rich editor is TipTap, which exposes its Editor on the ProseMirror DOM
 * node (`dom.editor`); its document is one paragraph with a hardBreak per
 * line. The plain editor is a textarea with one template line per text line.
 */

interface TipTapLike {
  state: {
    doc: {
      content: { size: number };
      descendants: (visit: (node: { type: { name: string } }, pos: number) => boolean | void) => void;
    };
  };
  chain: () => {
    focus: () => { setTextSelection: (pos: number) => { scrollIntoView: () => { run: () => boolean } } };
  };
}

/** The ProseMirror position where 1-based `line` starts, or null past the last line. */
export function lineStartPosition(editor: TipTapLike, line: number): number | null {
  if (line < 1) return null;
  if (line === 1) return 1;
  let seen = 0;
  let position: number | null = null;
  editor.state.doc.descendants((node, pos) => {
    if (position !== null) return false;
    if (node.type.name === "hardBreak") {
      seen += 1;
      if (seen === line - 1) position = pos + 1;
    }
    return true;
  });
  return position;
}

/** The textarea offset where 1-based `line` starts, or null past the last line. */
export function textOffsetOfLine(text: string, line: number): number | null {
  if (line < 1) return null;
  let offset = 0;
  for (let current = 1; current < line; current += 1) {
    const next = text.indexOf("\n", offset);
    if (next === -1) return null;
    offset = next + 1;
  }
  return offset;
}

/** Moves focus to the start of `line`. Returns false when no editor or no such line. */
export function jumpToTemplateLine(line: number, root: ParentNode = document): boolean {
  const rich = root.querySelector<HTMLElement & { editor?: TipTapLike }>('[aria-label="Template editor"]');
  if (rich?.editor) {
    const pos = lineStartPosition(rich.editor, line);
    if (pos === null) return false;
    return rich.editor.chain().focus().setTextSelection(pos).scrollIntoView().run();
  }
  const plain = root.querySelector<HTMLTextAreaElement>("#page-template-plain");
  if (plain) {
    const offset = textOffsetOfLine(plain.value, line);
    if (offset === null) return false;
    plain.focus();
    plain.setSelectionRange(offset, offset);
    plain.scrollIntoView?.({ block: "nearest" });
    return true;
  }
  return false;
}
