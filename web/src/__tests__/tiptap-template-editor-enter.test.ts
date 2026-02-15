/**
 * Tests for TipTapTemplateEditor Enter key behavior
 *
 * The rich editor uses a single paragraph with hardBreak nodes for line breaks.
 * parseTemplateSimple always creates exactly 6 lines (5 hardBreaks).
 * Enter should NAVIGATE to the next line (not insert a hardBreak).
 * Shift+Enter should be blocked entirely.
 *
 * These tests mirror the editor setup in TipTapTemplateEditor.tsx:
 *   - StarterKit with paragraph: true, hardBreak: true (no TemplateParagraph)
 *   - LineNavigation extension for Enter handling
 *   - Content from parseTemplateSimple (single paragraph with hardBreaks)
 */
import { describe, it, expect, afterEach } from 'vitest';
import { Editor } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import { LineNavigation } from '../components/tiptap-template-editor/extensions/line-navigation';
import {
  parseTemplateSimple,
  serializeTemplateSimple,
} from '../components/tiptap-template-editor/utils/serialization';

/** Count hardBreak nodes in the editor document */
function countHardBreaks(editor: Editor): number {
  let count = 0;
  editor.state.doc.descendants((node) => {
    if (node.type.name === 'hardBreak') {
      count++;
    }
  });
  return count;
}

/** Get all hardBreak positions */
function getHardBreakPositions(editor: Editor): number[] {
  const positions: number[] = [];
  editor.state.doc.descendants((node, pos) => {
    if (node.type.name === 'hardBreak') {
      positions.push(pos);
    }
  });
  return positions;
}

describe('LineNavigation Extension (Enter key)', () => {
  let editor: Editor;

  /** Create an editor matching the real TipTapTemplateEditor config */
  function createEditor(template: string): Editor {
    return new Editor({
      extensions: [
        StarterKit.configure({
          heading: false,
          blockquote: false,
          codeBlock: false,
          horizontalRule: false,
          bulletList: false,
          orderedList: false,
          listItem: false,
          code: false,
          bold: false,
          italic: false,
          strike: false,
          history: true,
          document: true,
          text: true,
          paragraph: true,
          hardBreak: true,
        }),
        LineNavigation,
      ],
      content: parseTemplateSimple(template),
    });
  }

  afterEach(() => {
    editor?.destroy();
  });

  // ── Document structure ────────────────────────────────────────────

  it('parseTemplateSimple always creates exactly 5 hardBreaks (6 lines)', () => {
    editor = createEditor('Hello');
    expect(countHardBreaks(editor)).toBe(5);

    editor.destroy();
    editor = createEditor('A\nB\nC\nD\nE\nF');
    expect(countHardBreaks(editor)).toBe(5);

    editor.destroy();
    editor = createEditor('');
    expect(countHardBreaks(editor)).toBe(5);
  });

  // ── goToNextLine navigates to next line ───────────────────────────

  it('should move cursor past the next hardBreak on goToNextLine', () => {
    editor = createEditor('LINE1\nLINE2\nLINE3\n\n\n');

    // Place cursor at beginning of line 1 (position 2 — inside paragraph)
    editor.commands.setTextSelection(2);
    const breakPositions = getHardBreakPositions(editor);

    // Trigger the command (this is what Enter key calls)
    editor.commands.goToNextLine();

    // Cursor should now be right after the first hardBreak
    const newPos = editor.state.selection.from;
    expect(newPos).toBe(breakPositions[0] + 1);
  });

  it('should advance through lines on consecutive goToNextLine calls', () => {
    editor = createEditor('A\nB\nC\nD\nE\nF');
    const breakPositions = getHardBreakPositions(editor);

    // Start on line 1
    editor.commands.setTextSelection(2);

    // Call goToNextLine 5 times to go through lines 2-6
    for (let i = 0; i < 5; i++) {
      editor.commands.goToNextLine();
      const cursorPos = editor.state.selection.from;
      expect(cursorPos).toBe(breakPositions[i] + 1);
    }
  });

  it('should wrap from last line back to first line', () => {
    editor = createEditor('A\nB\nC\nD\nE\nF');
    const breakPositions = getHardBreakPositions(editor);

    // Place cursor on the last line (after the last hardBreak)
    const lastBreak = breakPositions[breakPositions.length - 1];
    editor.commands.setTextSelection(lastBreak + 1);

    // goToNextLine should wrap to line 1
    editor.commands.goToNextLine();

    const newPos = editor.state.selection.from;
    // First content position inside the paragraph is 2
    expect(newPos).toBe(2);
  });

  // ── goToNextLine does NOT insert hardBreaks ───────────────────────

  it('should NOT change the number of hardBreaks', () => {
    editor = createEditor('LINE1\nLINE2\n\n\n\n');
    const breaksBefore = countHardBreaks(editor);

    editor.commands.setTextSelection(2);
    editor.commands.goToNextLine();

    expect(countHardBreaks(editor)).toBe(breaksBefore);
  });

  it('should NOT change the serialized content', () => {
    editor = createEditor('AAA\nBBB\nCCC\n\n\n');
    const serializedBefore = serializeTemplateSimple(editor.getJSON());

    editor.commands.setTextSelection(2);
    editor.commands.goToNextLine();

    expect(serializeTemplateSimple(editor.getJSON())).toBe(serializedBefore);
  });

  // ── goToNextLine from middle of line ──────────────────────────────

  it('should navigate to next line even when cursor is in the middle of text', () => {
    editor = createEditor('HELLO\nWORLD\n\n\n\n');
    const breakPositions = getHardBreakPositions(editor);

    // Place cursor in the middle of "HELLO" (after "HE")
    editor.commands.setTextSelection(4);

    editor.commands.goToNextLine();

    // Should be at the start of line 2 (after first hardBreak)
    const newPos = editor.state.selection.from;
    expect(newPos).toBe(breakPositions[0] + 1);
  });

  // ── Schema sanity ─────────────────────────────────────────────────

  it('should have hardBreak in the schema', () => {
    editor = createEditor('');
    expect(editor.state.schema.nodes.hardBreak).toBeDefined();
  });
});
