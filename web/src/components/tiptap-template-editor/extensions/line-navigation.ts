/**
 * LineNavigation Extension
 *
 * Handles Enter key in the single-paragraph / hardBreak document model.
 * Enter always inserts a hardBreak (line splitting). Validation of the
 * line count is handled externally (the parent shows a warning when over
 * the board limit, but doesn't prevent typing).
 *
 * Shift+Enter is blocked to prevent accidental double-breaks.
 */
import { Extension } from '@tiptap/core';

export interface LineNavigationOptions {
  maxLines: number;
}

export const LineNavigation = Extension.create<LineNavigationOptions>({
  name: 'lineNavigation',

  addOptions() {
    return {
      maxLines: 6,
    };
  },

  addKeyboardShortcuts() {
    return {
      'Enter': () => {
        return this.editor.commands.setHardBreak();
      },

      'Shift-Enter': () => true,
    };
  },
});
