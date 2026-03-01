/**
 * TrailingNewline Extension
 *
 * Ensures that a hardBreak at the end of a paragraph always has a ZWS
 * text node after it. Browsers collapse a bare trailing <br> inside a
 * block element, making the new empty line invisible. By appending a
 * zero-width space we give the line height and a cursor position.
 *
 * Runs as an appendTransaction plugin so it fires after any command
 * (setHardBreak, paste, undo, etc.) that might leave a trailing <br>.
 */
import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';

const CURSOR_ANCHOR = '\u200B';

export const TrailingNewline = Extension.create({
  name: 'trailingNewline',

  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: new PluginKey('trailingNewline'),

        appendTransaction(_transactions, _oldState, newState) {
          const { doc, tr } = newState;

          let modified = false;

          doc.descendants((node, pos) => {
            if (node.type.name !== 'paragraph') return;

            const lastChild = node.lastChild;
            if (!lastChild) return;

            if (lastChild.type.name === 'hardBreak') {
              const insertPos = pos + node.nodeSize - 1;
              tr.insertText(CURSOR_ANCHOR, insertPos);
              modified = true;
            }
          });

          return modified ? tr : null;
        },
      }),
    ];
  },
});
