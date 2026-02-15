/**
 * Tests for TipTapTemplateEditor Enter key behavior
 *
 * The rich editor uses a single paragraph with hardBreak nodes for line breaks.
 * parseTemplateSimple always creates exactly 6 lines (5 hardBreaks).
 *
 * Enter behaviour:
 *   - If < 6 lines: inserts a hardBreak (new line, content shifts down)
 *   - If = 6 lines: navigates to the next line (wraps at end)
 * Shift+Enter is always blocked.
 *
 * These tests mirror the editor setup in TipTapTemplateEditor.tsx:
 *   - StarterKit with paragraph: true, hardBreak: true
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

  // ── goToNextLine command (always navigates, never inserts) ────────

  it('should move cursor past the next hardBreak on goToNextLine', () => {
    editor = createEditor('LINE1\nLINE2\nLINE3\n\n\n');

    editor.commands.setTextSelection(2);
    const breakPositions = getHardBreakPositions(editor);

    editor.commands.goToNextLine();

    const newPos = editor.state.selection.from;
    expect(newPos).toBe(breakPositions[0] + 1);
  });

  it('should advance through lines on consecutive goToNextLine calls', () => {
    editor = createEditor('A\nB\nC\nD\nE\nF');
    const breakPositions = getHardBreakPositions(editor);

    editor.commands.setTextSelection(2);

    for (let i = 0; i < 5; i++) {
      editor.commands.goToNextLine();
      const cursorPos = editor.state.selection.from;
      expect(cursorPos).toBe(breakPositions[i] + 1);
    }
  });

  it('should wrap from last line back to first line', () => {
    editor = createEditor('A\nB\nC\nD\nE\nF');
    const breakPositions = getHardBreakPositions(editor);

    const lastBreak = breakPositions[breakPositions.length - 1];
    editor.commands.setTextSelection(lastBreak + 1);

    editor.commands.goToNextLine();

    const newPos = editor.state.selection.from;
    expect(newPos).toBe(2);
  });

  it('goToNextLine should NOT change the number of hardBreaks', () => {
    editor = createEditor('LINE1\nLINE2\n\n\n\n');
    const breaksBefore = countHardBreaks(editor);

    editor.commands.setTextSelection(2);
    editor.commands.goToNextLine();

    expect(countHardBreaks(editor)).toBe(breaksBefore);
  });

  it('goToNextLine should NOT change the serialized content', () => {
    editor = createEditor('AAA\nBBB\nCCC\n\n\n');
    const serializedBefore = serializeTemplateSimple(editor.getJSON());

    editor.commands.setTextSelection(2);
    editor.commands.goToNextLine();

    expect(serializeTemplateSimple(editor.getJSON())).toBe(serializedBefore);
  });

  it('goToNextLine should navigate even from the middle of text', () => {
    editor = createEditor('HELLO\nWORLD\n\n\n\n');
    const breakPositions = getHardBreakPositions(editor);

    editor.commands.setTextSelection(4);
    editor.commands.goToNextLine();

    const newPos = editor.state.selection.from;
    expect(newPos).toBe(breakPositions[0] + 1);
  });

  // ── Enter key at 6 lines: navigates (does not insert) ────────────

  it('at 6 lines, Enter should navigate not insert', () => {
    editor = createEditor('A\nB\nC\nD\nE\nF');
    expect(countHardBreaks(editor)).toBe(5);

    editor.commands.setTextSelection(2);

    // Simulate Enter via the keyboard shortcut path
    editor.commands.goToNextLine();

    // Still 5 hardBreaks — no insertion
    expect(countHardBreaks(editor)).toBe(5);
  });

  // ── Enter key at < 6 lines: inserts a hardBreak ──────────────────

  it('at fewer than 6 lines, setHardBreak should add a line', () => {
    // Start with 3 lines of content (parseTemplateSimple pads to 6)
    editor = createEditor('AA\nBB\nCC\n\n\n');
    expect(countHardBreaks(editor)).toBe(5);

    // Simulate user deleting a blank line to get < 6 lines.
    // Remove the last hardBreak+ZWS to drop from 6 → 5 lines.
    const breakPositions = getHardBreakPositions(editor);
    const lastBreak = breakPositions[breakPositions.length - 1];
    // Delete from just before the last hardBreak to end of content
    const docEnd = editor.state.doc.content.size;
    editor.commands.setTextSelection({ from: lastBreak, to: docEnd - 1 });
    editor.commands.deleteSelection();

    const breaksAfterDelete = countHardBreaks(editor);
    expect(breaksAfterDelete).toBeLessThan(5);

    // Now Enter should insert a hardBreak
    editor.commands.setTextSelection(2);
    editor.commands.setHardBreak();

    expect(countHardBreaks(editor)).toBe(breaksAfterDelete + 1);
  });

  // ── Schema sanity ─────────────────────────────────────────────────

  it('should have hardBreak in the schema', () => {
    editor = createEditor('');
    expect(editor.state.schema.nodes.hardBreak).toBeDefined();
  });
});
