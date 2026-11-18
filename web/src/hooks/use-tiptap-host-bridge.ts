import type { Editor, TiptapEditorHTMLElement } from "@tiptap/core";
import { type RefObject, useCallback, useEffect, useState, useSyncExternalStore } from "react";

/** Temporary host bridge: TipTap publishes its Editor on its own root DOM
 * element, but FiestaUI does not yet expose an editor/renderToolbar slot.
 * This TipTap DOM integration is not a FiestaUI public API.
 * Follow-up(FiestaUI): honor pickerPresentation on touch tools, then remove
 * this observer and the sibling toolbar without replacing the kit engine. */
export function useTiptapHostBridge(root: RefObject<HTMLElement | null>) {
  const [editor, setEditor] = useState<Editor | null>(null);
  useEffect(() => {
    const host = root.current;
    if (!host) return;
    const discover = () => {
      const element = host.querySelector<TiptapEditorHTMLElement>('[contenteditable="true"]');
      const candidate = element?.editor;
      const next = candidate && !candidate.isDestroyed ? candidate : null;
      setEditor((current) => (current === next ? current : next));
    };
    const observer = new MutationObserver(discover);
    observer.observe(host, { childList: true, subtree: true, attributes: true, attributeFilter: ["contenteditable"] });
    discover();
    return () => observer.disconnect();
  }, [root]);

  const subscribe = useCallback(
    (changed: () => void) => {
      if (!editor) return () => {};
      editor.on("selectionUpdate", changed);
      editor.on("transaction", changed);
      return () => {
        editor.off("selectionUpdate", changed);
        editor.off("transaction", changed);
      };
    },
    [editor],
  );
  const snapshot = useCallback(() => {
    if (!editor || editor.isDestroyed) return "0:0";
    const { doc, selection } = editor.state;
    let first = 0;
    let last = 0;
    // Match the kit's single-paragraph editor: hard breaks delimit lines,
    // and an alignment selection includes every line touched by the range.
    doc.nodesBetween(0, selection.from, (node) => {
      if (node.type.name === "hardBreak") first++;
    });
    last = first;
    if (!selection.empty)
      doc.nodesBetween(selection.from, selection.to, (node) => {
        if (node.type.name === "hardBreak") last++;
      });
    return `${first}:${last}`;
  }, [editor]);
  const selection = useSyncExternalStore(subscribe, snapshot, () => "0:0");
  const [firstLine, lastLine] = selection.split(":").map(Number);
  return { editor, firstLine, lastLine };
}
