/**
 * Tests for TipTap template serialization
 */
import { describe, it, expect } from 'vitest';
import {
  parseTemplate,
  serializeTemplate,
  parseTemplateSimple,
  serializeTemplateSimple,
} from '../components/tiptap-template-editor/utils/serialization';

describe('Template Serialization', () => {
  describe('parseTemplate', () => {
    it('parses plain text', () => {
      const template = 'Hello World';
      const doc = parseTemplate(template);
      
      expect(doc.type).toBe('doc');
      expect(doc.content).toHaveLength(6); // Always 6 lines
      expect(doc.content![0].content![0].type).toBe('text');
      expect(doc.content![0].content![0].text).toBe('Hello World');
    });

    it('parses variables', () => {
      const template = '{{weather.temp}}';
      const doc = parseTemplate(template);
      
      const firstNode = doc.content![0].content![0];
      expect(firstNode.type).toBe('variable');
      expect(firstNode.attrs?.pluginId).toBe('weather');
      expect(firstNode.attrs?.field).toBe('temp');
    });

    it('parses variables with filters', () => {
      const template = '{{weather.temp|pad:3}}';
      const doc = parseTemplate(template);
      
      const firstNode = doc.content![0].content![0];
      expect(firstNode.type).toBe('variable');
      expect(firstNode.attrs?.filters).toEqual([{ name: 'pad', arg: '3' }]);
    });

    it('parses color tiles', () => {
      const template = '{{red}} Alert {{red}}';
      const doc = parseTemplate(template);
      
      const line = doc.content![0].content!;
      expect(line[0].type).toBe('colorTile');
      expect(line[0].attrs?.color).toBe('red');
      expect(line[0].attrs?.code).toBe(63);
      expect(line[1].type).toBe('text');
      expect(line[1].text).toBe(' Alert ');
      expect(line[2].type).toBe('colorTile');
    });

    it('parses fill_space', () => {
      const template = 'Left{{fill_space}}Right';
      const doc = parseTemplate(template);
      
      const line = doc.content![0].content!;
      expect(line[0].text).toBe('Left');
      expect(line[1].type).toBe('fillSpace');
      expect(line[2].text).toBe('Right');
    });

    it('parses fill_space_repeat with dash', () => {
      const template = 'Header{{fill_space_repeat:-}}';
      const doc = parseTemplate(template);
      
      const line = doc.content![0].content!;
      expect(line[0].text).toBe('Header');
      expect(line[1].type).toBe('fillSpace');
      expect(line[1].attrs?.repeatChar).toBe('-');
    });

    it('parses fill_space_repeat with dot', () => {
      const template = 'A{{fill_space_repeat:.}}B';
      const doc = parseTemplate(template);
      
      const line = doc.content![0].content!;
      expect(line[0].text).toBe('A');
      expect(line[1].type).toBe('fillSpace');
      expect(line[1].attrs?.repeatChar).toBe('.');
      expect(line[2].text).toBe('B');
    });

    it('parses fill_space_repeat with multi-char', () => {
      const template = '{{fill_space_repeat:=-}}';
      const doc = parseTemplate(template);
      
      const line = doc.content![0].content!;
      expect(line[0].type).toBe('fillSpace');
      expect(line[0].attrs?.repeatChar).toBe('=-');
    });

    it('parses symbols', () => {
      const template = '{sun} Sunny {rain} Rainy';
      const doc = parseTemplate(template);
      
      const line = doc.content![0].content!;
      expect(line[0].type).toBe('symbol');
      expect(line[0].attrs?.symbol).toBe('sun');
      expect(line[0].attrs?.character).toBe('*');
      expect(line[1].text).toBe(' Sunny ');
      expect(line[2].type).toBe('symbol');
      expect(line[2].attrs?.symbol).toBe('rain');
      expect(line[2].attrs?.character).toBe('/');
    });

    it('parses alignment directives', () => {
      const template = '{center}Centered Text';
      const doc = parseTemplate(template);
      
      expect(doc.content![0].attrs?.alignment).toBe('center');
      expect(doc.content![0].content![0].text).toBe('Centered Text');
    });

    it('parses wrap directive', () => {
      const template = '{wrap}Wrapped Text';
      const doc = parseTemplate(template);
      
      expect(doc.content![0].attrs?.wrapEnabled).toBe(true);
      expect(doc.content![0].content![0].text).toBe('Wrapped Text');
    });

    it('parses wrap with alignment', () => {
      const template = '{wrap}{center}Centered Wrapped';
      const doc = parseTemplate(template);
      
      expect(doc.content![0].attrs?.wrapEnabled).toBe(true);
      expect(doc.content![0].attrs?.alignment).toBe('center');
      expect(doc.content![0].content![0].text).toBe('Centered Wrapped');
    });

    it('parses blank line with wrap', () => {
      const template = '{wrap}';
      const doc = parseTemplate(template);
      
      expect(doc.content![0].attrs?.wrapEnabled).toBe(true);
      expect(doc.content![0].content).toEqual([]);
    });

    it('parses blank line with wrap and alignment', () => {
      const template = '{wrap}{center}';
      const doc = parseTemplate(template);
      
      expect(doc.content![0].attrs?.wrapEnabled).toBe(true);
      expect(doc.content![0].attrs?.alignment).toBe('center');
      expect(doc.content![0].content).toEqual([]);
    });

    it('pads to 6 lines', () => {
      const template = 'Line 1\nLine 2';
      const doc = parseTemplate(template);
      
      expect(doc.content).toHaveLength(6);
      expect(doc.content![0].content).toHaveLength(1);
      expect(doc.content![1].content).toHaveLength(1);
      expect(doc.content![2].content).toEqual([]);
      expect(doc.content![3].content).toEqual([]);
    });

    it('truncates to 6 lines', () => {
      const template = 'L1\nL2\nL3\nL4\nL5\nL6\nL7\nL8';
      const doc = parseTemplate(template);
      
      expect(doc.content).toHaveLength(6);
    });
  });

  describe('serializeTemplate', () => {
    it('serializes plain text', () => {
      const doc = parseTemplate('Hello World');
      const serialized = serializeTemplate(doc);
      
      expect(serialized.split('\n')[0]).toBe('Hello World');
    });

    it('serializes variables', () => {
      const doc = parseTemplate('{{weather.temp}}');
      const serialized = serializeTemplate(doc);
      
      expect(serialized.split('\n')[0]).toBe('{{weather.temp}}');
    });

    it('serializes variables with filters', () => {
      const doc = parseTemplate('{{weather.temp|pad:3}}');
      const serialized = serializeTemplate(doc);
      
      expect(serialized.split('\n')[0]).toBe('{{weather.temp|pad:3}}');
    });

    it('serializes color tiles', () => {
      const doc = parseTemplate('{{red}} Alert');
      const serialized = serializeTemplate(doc);
      
      expect(serialized.split('\n')[0]).toBe('{{red}} Alert');
    });

    it('serializes fill_space', () => {
      const doc = parseTemplate('A{{fill_space}}B');
      const serialized = serializeTemplate(doc);
      
      expect(serialized.split('\n')[0]).toBe('A{{fill_space}}B');
    });

    it('serializes fill_space_repeat with dash', () => {
      const doc = parseTemplate('Header{{fill_space_repeat:-}}');
      const serialized = serializeTemplate(doc);
      
      expect(serialized.split('\n')[0]).toBe('Header{{fill_space_repeat:-}}');
    });

    it('serializes fill_space_repeat with dot', () => {
      const doc = parseTemplate('A{{fill_space_repeat:.}}B');
      const serialized = serializeTemplate(doc);
      
      expect(serialized.split('\n')[0]).toBe('A{{fill_space_repeat:.}}B');
    });

    it('serializes fill_space_repeat with multi-char', () => {
      const doc = parseTemplate('{{fill_space_repeat:=-}}');
      const serialized = serializeTemplate(doc);
      
      expect(serialized.split('\n')[0]).toBe('{{fill_space_repeat:=-}}');
    });

    it('serializes symbols', () => {
      const doc = parseTemplate('{sun} {rain}');
      const serialized = serializeTemplate(doc);
      
      expect(serialized.split('\n')[0]).toBe('{sun} {rain}');
    });

    it('serializes alignment', () => {
      const doc = parseTemplate('{center}Centered');
      const serialized = serializeTemplate(doc);
      
      expect(serialized.split('\n')[0]).toBe('{center}Centered');
    });

    it('serializes wrap directive', () => {
      const doc = parseTemplate('{wrap}Wrapped Text');
      const serialized = serializeTemplate(doc);
      
      expect(serialized.split('\n')[0]).toBe('{wrap}Wrapped Text');
    });

    it('serializes wrap with alignment', () => {
      const doc = parseTemplate('{wrap}{center}Centered Wrapped');
      const serialized = serializeTemplate(doc);
      
      expect(serialized.split('\n')[0]).toBe('{wrap}{center}Centered Wrapped');
    });

    it('serializes blank line with wrap', () => {
      const doc = parseTemplate('{wrap}');
      const serialized = serializeTemplate(doc);
      
      expect(serialized.split('\n')[0]).toBe('{wrap}');
    });

    it('serializes blank line with wrap and alignment', () => {
      const doc = parseTemplate('{wrap}{center}');
      const serialized = serializeTemplate(doc);
      
      expect(serialized.split('\n')[0]).toBe('{wrap}{center}');
    });

    it('serializes blank line with wrap and right alignment', () => {
      const doc = parseTemplate('{wrap}{right}');
      const serialized = serializeTemplate(doc);
      
      expect(serialized.split('\n')[0]).toBe('{wrap}{right}');
    });

    it('always produces 6 lines', () => {
      const doc = parseTemplate('One line');
      const serialized = serializeTemplate(doc);
      
      const lines = serialized.split('\n');
      expect(lines).toHaveLength(6);
      expect(lines[0]).toBe('One line');
      expect(lines[1]).toBe('');
      expect(lines[5]).toBe('');
    });
  });

  describe('Round-trip consistency', () => {
    it('maintains plain text', () => {
      const original = 'Hello\nWorld\n\n\n\n';
      const doc = parseTemplate(original);
      const serialized = serializeTemplate(doc);
      
      expect(serialized).toBe(original);
    });

    it('maintains complex template', () => {
      const original = '{{red}} {{weather.temp|pad:3}}F\n{sun} {rain}\nLeft{{fill_space}}Right\n{center}Centered\n\n';
      const doc = parseTemplate(original);
      const serialized = serializeTemplate(doc);
      
      expect(serialized).toBe(original);
    });

    it('maintains fill_space_repeat', () => {
      const original = 'Header{{fill_space_repeat:-}}\n{{fill_space_repeat:.}}\nA{{fill_space}}B\n\n\n';
      const doc = parseTemplate(original);
      const serialized = serializeTemplate(doc);
      
      expect(serialized).toBe(original);
    });

    it('maintains blank line with wrap', () => {
      const original = 'Line 1\n{wrap}\nLine 3\n\n\n';
      const doc = parseTemplate(original);
      const serialized = serializeTemplate(doc);
      
      expect(serialized).toBe(original);
    });

    it('maintains blank line with wrap between content lines', () => {
      const original = 'First Line\n{wrap}\nThird Line\n\n\n';
      const doc = parseTemplate(original);
      const serialized = serializeTemplate(doc);
      
      expect(serialized).toBe(original);
    });

    it('maintains blank line with wrap and alignment', () => {
      const original = 'Line 1\n{wrap}{center}\nLine 3\n\n\n';
      const doc = parseTemplate(original);
      const serialized = serializeTemplate(doc);
      
      expect(serialized).toBe(original);
    });

    it('maintains multiple blank lines with wrap', () => {
      const original = 'Line 1\n{wrap}\n{wrap}\nLine 4\n\n';
      const doc = parseTemplate(original);
      const serialized = serializeTemplate(doc);
      
      expect(serialized).toBe(original);
    });

    it('maintains wrap on content line', () => {
      const original = '{wrap}Wrapped Content\nRegular Line\n\n\n\n';
      const doc = parseTemplate(original);
      const serialized = serializeTemplate(doc);
      
      expect(serialized).toBe(original);
    });

    it('maintains complex template with wrap on blank lines', () => {
      const original = '{{red}} Alert\n{wrap}\n{center}Centered\n{wrap}{right}\n\n';
      const doc = parseTemplate(original);
      const serialized = serializeTemplate(doc);
      
      expect(serialized).toBe(original);
    });
  });
});

// =====================================================================
// parseTemplateSimple / serializeTemplateSimple – 3-line mode (Note)
// =====================================================================

describe('Simple serialization – 3-line mode (Note)', () => {
  describe('parseTemplateSimple with maxLines=3', () => {
    it('creates a doc with exactly 2 hardBreaks for 3 lines', () => {
      const doc = parseTemplateSimple('A\nB\nC', 3);
      const para = doc.content![0];
      const hardBreaks = para.content!.filter(n => n.type === 'hardBreak');
      expect(hardBreaks).toHaveLength(2);
    });

    it('pads single-line input to 3 lines', () => {
      const doc = parseTemplateSimple('ONLY', 3);
      const para = doc.content![0];
      const hardBreaks = para.content!.filter(n => n.type === 'hardBreak');
      expect(hardBreaks).toHaveLength(2);
    });

    it('truncates input beyond 3 lines', () => {
      const doc = parseTemplateSimple('A\nB\nC\nD\nE', 3);
      const para = doc.content![0];
      const hardBreaks = para.content!.filter(n => n.type === 'hardBreak');
      expect(hardBreaks).toHaveLength(2);
    });

    it('empty string still has 2 hardBreaks', () => {
      const doc = parseTemplateSimple('', 3);
      const para = doc.content![0];
      const hardBreaks = para.content!.filter(n => n.type === 'hardBreak');
      expect(hardBreaks).toHaveLength(2);
    });
  });

  describe('serializeTemplateSimple with maxLines=3', () => {
    it('produces exactly 3 lines', () => {
      const doc = parseTemplateSimple('HELLO\nWORLD\n', 3);
      const serialized = serializeTemplateSimple(doc, 3);
      const lines = serialized.split('\n');
      expect(lines).toHaveLength(3);
    });

    it('pads short content to 3 lines', () => {
      const doc = parseTemplateSimple('HI', 3);
      const serialized = serializeTemplateSimple(doc, 3);
      const lines = serialized.split('\n');
      expect(lines).toHaveLength(3);
      expect(lines[0]).toBe('HI');
      expect(lines[1]).toBe('');
      expect(lines[2]).toBe('');
    });

    it('empty doc with maxLines=3 produces 3 empty lines', () => {
      const doc = parseTemplateSimple('', 3);
      const serialized = serializeTemplateSimple(doc, 3);
      expect(serialized).toBe('\n\n');
    });
  });

  describe('Round-trip (3-line mode)', () => {
    it('round-trips 3 lines of plain text', () => {
      const original = 'ONE\nTWO\nTHREE';
      const doc = parseTemplateSimple(original, 3);
      const serialized = serializeTemplateSimple(doc, 3);
      expect(serialized).toBe(original);
    });

    it('round-trips Note template with variables', () => {
      const original = '{{weather.temp}}\n{{red}}\n';
      const doc = parseTemplateSimple(original, 3);
      const serialized = serializeTemplateSimple(doc, 3);
      expect(serialized).toBe(original);
    });

    it('round-trips Note template with fill_space', () => {
      const original = 'A{{fill_space}}B\n\n';
      const doc = parseTemplateSimple(original, 3);
      const serialized = serializeTemplateSimple(doc, 3);
      expect(serialized).toBe(original);
    });
  });
});
