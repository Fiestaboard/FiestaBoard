/**
 * LineNavigation Extension
 *
 * Handles Enter key in the single-paragraph / hardBreak document model.
 *
 * Behaviour:
 *  - If the document has fewer lines than `maxLines` (configurable, default 6),
 *    Enter inserts a hardBreak — content below shifts down.
 *  - If the document already has `maxLines` lines, Enter moves the cursor to
 *    the start of the next line (wrapping from the last line back to line 1).
 *  - Shift+Enter is always blocked to prevent accidental hardBreak insertion.
 *
 * Configure per device type:
 *   LineNavigation.configure({ maxLines: 3 })  // Vestaboard Note
 *   LineNavigation.configure({ maxLines: 6 })  // Vestaboard Flagship (default)
 */
import { Extension } from '@tiptap/core';
import { TextSelection } from '@tiptap/pm/state';

export interface LineNavigationOptions {
  maxLines: number;
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    lineNavigation: {
      goToNextLine: () => ReturnType;
    };
  }
}

export const LineNavigation = Extension.create<LineNavigationOptions>({
  name: 'lineNavigation',

  addOptions() {
    return {
      maxLines: 6,
    };
  },

  addCommands() {
    return {
      goToNextLine:
        () =>
        ({ tr, dispatch }) => {
          const cursorPos = tr.selection.$from.pos;

          const hardBreakPositions: number[] = [];
          tr.doc.descendants((node, pos) => {
            if (node.type.name === 'hardBreak') {
              hardBreakPositions.push(pos);
            }
          });

          const nextBreakPos = hardBreakPositions.find(pos => pos > cursorPos);

          let targetPos: number;

          if (nextBreakPos !== undefined) {
            targetPos = nextBreakPos + 1;
          } else {
            targetPos = 2;
          }

          if (dispatch) {
            tr.setSelection(TextSelection.create(tr.doc, targetPos));
            dispatch(tr);
          }

          return true;
        },
    };
  },

  addKeyboardShortcuts() {
    return {
      'Enter': () => {
        const { state } = this.editor;
        const { maxLines } = this.options;

        let hardBreakCount = 0;
        state.doc.descendants((node) => {
          if (node.type.name === 'hardBreak') {
            hardBreakCount++;
          }
        });

        if (hardBreakCount < maxLines - 1) {
          return this.editor.commands.setHardBreak();
        }

        return this.editor.commands.goToNextLine();
      },

      'Shift-Enter': () => true,
    };
  },
});
