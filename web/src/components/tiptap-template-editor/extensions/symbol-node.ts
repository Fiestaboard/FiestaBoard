/**
 * SymbolNode - Inline node for {sun}, {cloud}, etc.
 * Renders ACTUAL FiestaBoard characters (NOT icons) for true WYSIWYG
 */
import { Node, mergeAttributes } from '@tiptap/core';
import { ReactNodeViewRenderer } from '@tiptap/react';
import { SymbolNodeView } from '../node-views/SymbolNodeView';

export interface SymbolAttrs {
  symbol: string;
  character: string;
}

export const SymbolNode = Node.create({
  name: 'symbol',

  group: 'inline',

  inline: true,

  atom: true, // Single unit, non-editable

  selectable: false, // Treat as character: arrow keys skip past, shift+arrow selects

  draggable: true, // TipTap-managed drag (integrates with ProseMirror events)

  addAttributes() {
    return {
      symbol: {
        default: 'sun',
        parseHTML: element => element.getAttribute('data-symbol'),
        renderHTML: attributes => ({
          'data-symbol': attributes.symbol,
        }),
      },
      character: {
        default: '*',
        parseHTML: element => element.getAttribute('data-character'),
        renderHTML: attributes => ({
          'data-character': attributes.character,
        }),
      },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'span[data-type="symbol"]',
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return ['span', mergeAttributes({ 'data-type': 'symbol' }, HTMLAttributes)];
  },

  addNodeView() {
    return ReactNodeViewRenderer(SymbolNodeView);
  },
});
