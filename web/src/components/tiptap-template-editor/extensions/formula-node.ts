/**
 * FormulaNode — Inline atom node for {{= expression }} formulas.
 * Rendered as a clickable amber badge pill (FormulaNodeView).
 */
import { Node, mergeAttributes } from '@tiptap/core';
import { ReactNodeViewRenderer } from '@tiptap/react';
import { FormulaNodeView } from '../node-views/FormulaNodeView';

export const FormulaNode = Node.create({
  name: 'formula',

  group: 'inline',

  inline: true,

  atom: true,

  selectable: false,

  draggable: true,

  addAttributes() {
    return {
      expression: {
        default: '',
        parseHTML: element => element.getAttribute('data-expression') ?? '',
        renderHTML: attributes => ({
          'data-expression': attributes.expression,
        }),
      },
      // Ephemeral flag — NOT serialized to HTML. Set to true on fresh insertion
      // so FormulaNodeView knows to auto-open the editor panel.
      autoOpen: {
        default: false,
        parseHTML: () => false,   // always false when loaded from HTML
        renderHTML: () => ({}),   // never written to DOM
      },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'span[data-type="formula"]',
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return ['span', mergeAttributes({ 'data-type': 'formula' }, HTMLAttributes)];
  },

  addNodeView() {
    return ReactNodeViewRenderer(FormulaNodeView);
  },
});
