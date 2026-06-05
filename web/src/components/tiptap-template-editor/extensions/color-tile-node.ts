/**
 * ColorTileNode - Inline node for {{red}}, {{blue}}, etc.
 * Renders as actual colored tiles matching FiestaBoard hardware
 */
import { mergeAttributes, Node } from "@tiptap/core";
import { ReactNodeViewRenderer } from "@tiptap/react";

import { ColorTileNodeView } from "../node-views/ColorTileNodeView";

export interface ColorTileAttrs {
  color: string;
  code: number;
}

export const ColorTileNode = Node.create({
  name: "colorTile",

  group: "inline",

  inline: true,

  atom: true, // Single unit, non-editable

  selectable: false, // Treat as character: arrow keys skip past, shift+arrow selects

  draggable: true, // TipTap-managed drag (integrates with ProseMirror events)

  addAttributes() {
    return {
      color: {
        default: "red",
        parseHTML: (element) => element.getAttribute("data-color"),
        renderHTML: (attributes) => ({
          "data-color": attributes.color,
        }),
      },
      code: {
        default: 63,
        parseHTML: (element) => {
          const code = element.getAttribute("data-code");
          return code ? parseInt(code, 10) : 63;
        },
        renderHTML: (attributes) => ({
          "data-code": attributes.code?.toString() || "63",
        }),
      },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'span[data-type="color-tile"]',
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return ["span", mergeAttributes({ "data-type": "color-tile" }, HTMLAttributes)];
  },

  addNodeView() {
    return ReactNodeViewRenderer(ColorTileNodeView);
  },
});
