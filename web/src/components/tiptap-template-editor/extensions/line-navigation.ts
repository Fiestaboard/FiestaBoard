/**
 * LineNavigation Extension
 *
 * Handles Enter key in the single-paragraph / hardBreak document model.
 * Enter always inserts a hardBreak (line splitting). Validation of the
 * line count is handled externally (the parent shows a warning when over
 * the board limit, but doesn't prevent typing).
 *
 * Shift+Enter is blocked to prevent accidental double-breaks.
 *
 * NOTE: In the full TipTapTemplateEditor, the editorProps `handleKeyDown`
 * intercepts Enter/Shift-Enter before plugin keymaps run, so the shortcuts
 * below are effectively redundant at runtime. They are retained so that
 * unit tests (which instantiate a bare Editor with this extension but
 * without editorProps) still get correct Enter-as-hardBreak behavior.
 */
import { Extension } from "@tiptap/core";

export const LineNavigation = Extension.create({
  name: "lineNavigation",

  priority: 1000,

  addKeyboardShortcuts() {
    return {
      Enter: () => {
        this.editor.commands.setHardBreak();
        return true;
      },

      "Shift-Enter": () => true,
    };
  },
});
