/**
 * WrappedTextNode - Inline node for text that will be wrapped
 * Created when user selects text and applies wrap filter
 */
import { mergeAttributes, Node } from "@tiptap/core";
import { ReactNodeViewRenderer } from "@tiptap/react";

import { WrappedTextView } from "../node-views/WrappedTextView";

export interface WrappedTextAttrs {
  text: string;
}

export const WrappedTextNode = Node.create({
  name: "wrappedText",

  group: "inline",

  inline: true,

  atom: false, // Allow editing

  addAttributes() {
    return {
      text: {
        default: "",
        parseHTML: (element) => element.getAttribute("data-text") || element.textContent || "",
        renderHTML: (attributes) => ({
          "data-text": attributes.text,
        }),
      },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'span[data-type="wrapped-text"]',
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return ["span", mergeAttributes({ "data-type": "wrapped-text" }, HTMLAttributes)];
  },

  addNodeView() {
    return ReactNodeViewRenderer(WrappedTextView);
  },
});
