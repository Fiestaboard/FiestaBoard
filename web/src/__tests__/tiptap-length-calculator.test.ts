/**
 * Tests for line length calculation
 */
import { describe, it, expect } from 'vitest';
import { calculateLineLength, willOverflow, getOverflowAmount } from '../components/tiptap-template-editor/utils/length-calculator';
import { JSONContent } from '@tiptap/react';

describe('Length Calculator', () => {
  describe('calculateLineLength', () => {
    it('calculates plain text length', () => {
      const content: JSONContent[] = [
        { type: 'text', text: 'Hello World' }
      ];
      
      expect(calculateLineLength(content)).toBe(11);
    });

    it('counts color tiles as 1 character', () => {
      const content: JSONContent[] = [
        { type: 'colorTile', attrs: { color: 'red', code: 63 } },
        { type: 'text', text: ' Alert ' },
        { type: 'colorTile', attrs: { color: 'red', code: 63 } },
      ];
      
      expect(calculateLineLength(content)).toBe(9); // 1 + 7 + 1
    });

    it('counts variables by maxLength', () => {
      const content: JSONContent[] = [
        { type: 'variable', attrs: { pluginId: 'weather', field: 'temp', maxLength: 3 } },
        { type: 'text', text: 'F' },
      ];
      
      expect(calculateLineLength(content)).toBe(4); // 3 + 1
    });

    it('counts fill_space as 0', () => {
      const content: JSONContent[] = [
        { type: 'text', text: 'Left' },
        { type: 'fillSpace', attrs: { id: '123' } },
        { type: 'text', text: 'Right' },
      ];
      
      expect(calculateLineLength(content)).toBe(9); // 4 + 0 + 5
    });

    it('handles empty content', () => {
      expect(calculateLineLength([])).toBe(0);
    });
  });

  describe('willOverflow', () => {
    it('detects no overflow', () => {
      const content: JSONContent[] = [
        { type: 'text', text: 'Short' }
      ];
      
      expect(willOverflow(content)).toBe(false);
    });

    it('detects overflow', () => {
      const content: JSONContent[] = [
        { type: 'text', text: 'This is a very long line that exceeds twenty-two characters' }
      ];
      
      expect(willOverflow(content)).toBe(true);
    });

    it('handles exactly 22 characters as no overflow', () => {
      const content: JSONContent[] = [
        { type: 'text', text: '1234567890123456789012' } // Exactly 22
      ];
      
      expect(willOverflow(content)).toBe(false);
    });
  });

  describe('getOverflowAmount', () => {
    it('returns 0 for no overflow', () => {
      const content: JSONContent[] = [
        { type: 'text', text: 'Short' }
      ];
      
      expect(getOverflowAmount(content)).toBe(0);
    });

    it('calculates overflow amount', () => {
      const content: JSONContent[] = [
        { type: 'text', text: '12345678901234567890123456' } // 26 chars
      ];
      
      expect(getOverflowAmount(content)).toBe(4); // 26 - 22
    });
  });
});
