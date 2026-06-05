/**
 * SingleParagraphDoc Extension
 *
 * Overrides the default Document node to allow EXACTLY one paragraph.
 * This prevents ProseMirror's built-in `splitBlock` command (bound to
 * Enter in the base keymap) from ever creating a second paragraph.
 *
 * Without this, a race condition or priority mis-ordering could let
 * splitBlock run, which would:
 *   1. Create two <p> nodes,
 *   2. Place the cursor at position 0 of the second <p>,
 *   3. Confuse the serializer (which reads only the first <p>).
 */
import { Node } from "@tiptap/core";

export const SingleParagraphDoc = Node.create({
  name: "doc",
  topNode: true,
  content: "paragraph",
});
