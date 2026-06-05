/**
 * VariableNode - Inline node for {{plugin.field}} variables
 * Supports filters like |pad:3, |wrap, etc.
 */
import { mergeAttributes, Node } from "@tiptap/core";
import { ReactNodeViewRenderer } from "@tiptap/react";

import { VariableNodeView } from "../node-views/VariableNodeView";

export interface VariableAttrs {
  pluginId: string;
  field: string;
  filters: Array<{ name: string; arg?: string }>;
  maxLength?: number;
}

export const VariableNode = Node.create({
  name: "variable",

  group: "inline",

  inline: true,

  atom: true, // Treat as single unit (non-editable, non-splittable)

  selectable: false, // Treat as character: arrow keys skip past, shift+arrow selects

  draggable: true, // TipTap-managed drag (integrates with ProseMirror events)

  addAttributes() {
    return {
      pluginId: {
        default: "",
        parseHTML: (element) => element.getAttribute("data-plugin-id"),
        renderHTML: (attributes) => ({
          "data-plugin-id": attributes.pluginId,
        }),
      },
      field: {
        default: "",
        parseHTML: (element) => element.getAttribute("data-field"),
        renderHTML: (attributes) => ({
          "data-field": attributes.field,
        }),
      },
      filters: {
        default: [],
        parseHTML: (element) => {
          const filtersStr = element.getAttribute("data-filters");
          return filtersStr ? JSON.parse(filtersStr) : [];
        },
        renderHTML: (attributes) => ({
          "data-filters": JSON.stringify(attributes.filters || []),
        }),
      },
      maxLength: {
        default: 10,
        parseHTML: (element) => {
          const maxLen = element.getAttribute("data-max-length");
          return maxLen ? parseInt(maxLen, 10) : 10;
        },
        renderHTML: (attributes) => ({
          "data-max-length": attributes.maxLength?.toString() || "10",
        }),
      },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'span[data-type="variable"]',
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return ["span", mergeAttributes({ "data-type": "variable" }, HTMLAttributes)];
  },

  addNodeView() {
    return ReactNodeViewRenderer(VariableNodeView);
  },
});
