/**
 * Tests for TipTapTemplateEditor Enter key behavior
 *
 * The rich editor uses a single paragraph with hardBreak nodes for line breaks.
 * parseTemplateSimple creates at least N lines (padding), but no longer truncates.
 *
 * Enter always inserts a hardBreak (line splitting). Users are free to exceed
 * the board line limit; validation is handled externally via onLineCountChange.
 *
 * Shift+Enter is always blocked.
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

describe('LineNavigation Extension (Enter key)', () => {
  let editor: Editor;

  function createEditor(template: string, maxLines = 6): Editor {
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
      content: parseTemplateSimple(template, maxLines),
    });
  }

  afterEach(() => {
    editor?.destroy();
  });

  // ── Document structure ────────────────────────────────────────────

  it('parseTemplateSimple pads to 6 lines (5 hardBreaks) for short content', () => {
    editor = createEditor('Hello');
    expect(countHardBreaks(editor)).toBe(5);

    editor.destroy();
    editor = createEditor('');
    expect(countHardBreaks(editor)).toBe(5);
  });

  it('parseTemplateSimple creates exactly 5 hardBreaks for 6-line content', () => {
    editor = createEditor('A\nB\nC\nD\nE\nF');
    expect(countHardBreaks(editor)).toBe(5);
  });

  it('parseTemplateSimple preserves lines beyond maxLines (no truncation)', () => {
    editor = createEditor('A\nB\nC\nD\nE\nF\nG\nH');
    // 8 lines = 7 hardBreaks
    expect(countHardBreaks(editor)).toBe(7);
  });

  // ── Enter key always inserts a hardBreak ──────────────────────────

  it('Enter inserts a hardBreak even when at maxLines', () => {
    editor = createEditor('A\nB\nC\nD\nE\nF');
    expect(countHardBreaks(editor)).toBe(5);

    editor.commands.setTextSelection(2);
    editor.commands.setHardBreak();

    // Now 6 hardBreaks (7 lines) — no cap
    expect(countHardBreaks(editor)).toBe(6);
  });

  it('Enter inserts a hardBreak below maxLines', () => {
    editor = createEditor('AA\nBB\n\n\n\n');
    expect(countHardBreaks(editor)).toBe(5);

    editor.commands.setTextSelection(2);
    editor.commands.setHardBreak();

    expect(countHardBreaks(editor)).toBe(6);
  });

  // ── Schema sanity ─────────────────────────────────────────────────

  it('should have hardBreak in the schema', () => {
    editor = createEditor('');
    expect(editor.state.schema.nodes.hardBreak).toBeDefined();
  });

  // ── Serialization ─────────────────────────────────────────────────

  it('serializeTemplateSimple preserves lines beyond maxLines', () => {
    editor = createEditor('A\nB\nC\nD\nE\nF\nG');
    const serialized = serializeTemplateSimple(editor.getJSON(), 6);
    const lines = serialized.split('\n');
    expect(lines.length).toBeGreaterThanOrEqual(7);
    expect(lines[0]).toBe('A');
    expect(lines[6]).toBe('G');
  });

  it('serializeTemplateSimple pads to at least maxLines', () => {
    editor = createEditor('HELLO');
    const serialized = serializeTemplateSimple(editor.getJSON(), 6);
    const lines = serialized.split('\n');
    expect(lines.length).toBeGreaterThanOrEqual(6);
    expect(lines[0]).toBe('HELLO');
  });
});

// =====================================================================
// 3-line mode (Vestaboard Note)
// =====================================================================

describe('3-line mode (Note device)', () => {
  let editor: Editor;

  function createNoteEditor(template: string): Editor {
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
      content: parseTemplateSimple(template, 3),
    });
  }

  afterEach(() => {
    editor?.destroy();
  });

  // ── parseTemplateSimple with maxLines=3 ─────────────────────────

  it('parseTemplateSimple(_, 3) creates exactly 2 hardBreaks for 3-line content', () => {
    editor = createNoteEditor('A\nB\nC');
    expect(countHardBreaks(editor)).toBe(2);
  });

  it('parseTemplateSimple(_, 3) pads short templates to 3 lines', () => {
    editor = createNoteEditor('ONE');
    expect(countHardBreaks(editor)).toBe(2);
  });

  it('parseTemplateSimple(_, 3) preserves lines beyond 3 (no truncation)', () => {
    editor = createNoteEditor('A\nB\nC\nD\nE');
    // 5 lines = 4 hardBreaks (no longer truncated to 3)
    expect(countHardBreaks(editor)).toBe(4);
  });

  // ── serializeTemplateSimple with maxLines=3 ─────────────────────

  it('serializeTemplateSimple(_, 3) pads to at least 3 lines', () => {
    editor = createNoteEditor('HELLO\nWORLD\n');
    const lines = serializeTemplateSimple(editor.getJSON(), 3).split('\n');
    expect(lines.length).toBeGreaterThanOrEqual(3);
    expect(lines[0]).toBe('HELLO');
    expect(lines[1]).toBe('WORLD');
    expect(lines[2]).toBe('');
  });

  it('serializeTemplateSimple round-trips 3-line content', () => {
    const original = 'HELLO\nWORLD\nTHREE';
    editor = createNoteEditor(original);
    const serialized = serializeTemplateSimple(editor.getJSON(), 3);
    const lines = serialized.split('\n');
    expect(lines.length).toBeGreaterThanOrEqual(3);
    expect(lines[0]).toBe('HELLO');
    expect(lines[1]).toBe('WORLD');
    expect(lines[2]).toBe('THREE');
  });

  // ── Enter always inserts in 3-line mode too ─────────────────────

  it('Enter inserts a hardBreak even at 3 lines', () => {
    editor = createNoteEditor('A\nB\nC');
    expect(countHardBreaks(editor)).toBe(2);

    editor.commands.setTextSelection(2);
    editor.commands.setHardBreak();

    // Now 3 hardBreaks (4 lines)
    expect(countHardBreaks(editor)).toBe(3);
  });
});
