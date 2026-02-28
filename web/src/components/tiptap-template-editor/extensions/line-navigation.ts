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
 * Uses priority 1000 so our Enter handler runs before the default Keymap's
 * splitBlock, which would create new paragraphs instead of inserting hardBreaks.
 */
import { Extension } from '@tiptap/core';

export const LineNavigation = Extension.create({
  name: 'lineNavigation',

  priority: 1000,

  addKeyboardShortcuts() {
    return {
      'Enter': () => {
        this.editor.commands.setHardBreak();
        return true;
      },

      'Shift-Enter': () => true,
    };
  },
});
