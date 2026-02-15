/**
 * LineNavigation Extension
 *
 * Handles Enter key in the single-paragraph / hardBreak document model.
 *
 * Behaviour:
 *  - If the document has fewer than 6 lines (< 5 hardBreaks), Enter inserts
 *    a hardBreak at the cursor position — content below shifts down and a new
 *    blank line appears.  This matches what users expect from a normal editor.
 *  - If the document already has 6 lines, Enter moves the cursor to the start
 *    of the next line (wrapping from line 6 back to line 1).
 *  - Shift+Enter is always blocked to prevent accidental hardBreak insertion.
 */
import { Extension } from '@tiptap/core';
import { TextSelection } from '@tiptap/pm/state';

/** Maximum lines the template supports. */
const MAX_LINES = 6;

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    lineNavigation: {
      /**
       * Move cursor to the start of the next line (wrapping at the end).
       */
      goToNextLine: () => ReturnType;
    };
  }
}

export const LineNavigation = Extension.create({
  name: 'lineNavigation',

  addCommands() {
    return {
      goToNextLine:
        () =>
        ({ tr, dispatch }) => {
          const cursorPos = tr.selection.$from.pos;

          // Collect every hardBreak position in document order
          const hardBreakPositions: number[] = [];
          tr.doc.descendants((node, pos) => {
            if (node.type.name === 'hardBreak') {
              hardBreakPositions.push(pos);
            }
          });

          // Find the first hardBreak that comes after the cursor
          const nextBreakPos = hardBreakPositions.find(pos => pos > cursorPos);

          let targetPos: number;

          if (nextBreakPos !== undefined) {
            // Move cursor to just after the hardBreak (hardBreak nodeSize = 1)
            targetPos = nextBreakPos + 1;
          } else {
            // Cursor is on or past the last line — wrap to line 1.
            // In our doc model: doc opens at 0, paragraph opens at 1,
            // so the first content position inside the paragraph is 2.
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

        // Count current hardBreaks to know how many lines we have.
        let hardBreakCount = 0;
        state.doc.descendants((node) => {
          if (node.type.name === 'hardBreak') {
            hardBreakCount++;
          }
        });

        // Room to add a line? Insert a hardBreak (natural behaviour).
        if (hardBreakCount < MAX_LINES - 1) {
          return this.editor.commands.setHardBreak();
        }

        // Already at 6 lines — just navigate to the next line.
        return this.editor.commands.goToNextLine();
      },

      // Block Shift+Enter so no extra hardBreaks are inserted
      'Shift-Enter': () => true,
    };
  },
});
