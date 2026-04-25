/**
 * Utility functions for inserting template content into TipTap editor
 * at the current cursor position
 */

import { Editor } from '@tiptap/react';
import { parseLineContent } from './serialization';

/**
 * Insert template content at the current cursor position in the editor
 * @param editor - The TipTap editor instance
 * @param templateString - Template string to insert (e.g., "{{weather.temperature}}", "{red}", "{{fill_space}}")
 */
export function insertTemplateContent(
  editor: Editor,
  templateString: string
): void {
  if (!editor || !editor.state) {
    console.warn('Cannot insert content: editor is not available or not initialized');
    return;
  }

  // Parse the template string into TipTap nodes
  const nodes = parseLineContent(templateString);
  
  if (nodes.length === 0) {
    return;
  }

  // Get current cursor position before insertion
  if (!editor.state.selection) {
    console.warn('Cannot insert content: editor selection is not available');
    return;
  }
  
  const { from } = editor.state.selection;
  
  // Insert at current cursor position
  editor.chain().focus().insertContent(nodes).run();
  
  // Calculate the size of inserted content to position cursor correctly
  // For atomic nodes, we need to move cursor past the node
  let insertedSize = 0;
  nodes.forEach((_node: any) => {
    // Atomic nodes (color tiles, variables, etc.) take 1 position
    insertedSize += 1;
  });
  
  // Set cursor position after the inserted content
  const newPosition = from + insertedSize;
  editor.commands.setTextSelection(newPosition);
}
