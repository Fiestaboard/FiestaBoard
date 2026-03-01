import { describe, it, expect } from 'vitest';
import {
  BOARD_COLORS,
  COLOR_CODE_MAP,
  ALL_COLOR_CODES,
  AVAILABLE_COLORS,
  getBoardColor,
  isValidBoardColor,
} from '../src/board-colors';

describe('board-colors', () => {
  describe('BOARD_COLORS', () => {
    it('has all 8 official colors', () => {
      expect(BOARD_COLORS.red).toBe('#eb4034');
      expect(BOARD_COLORS.orange).toBe('#f5a623');
      expect(BOARD_COLORS.yellow).toBe('#f8e71c');
      expect(BOARD_COLORS.green).toBe('#7ed321');
      expect(BOARD_COLORS.blue).toBe('#4a90d9');
      expect(BOARD_COLORS.violet).toBe('#9b59b6');
      expect(BOARD_COLORS.white).toBe('#ffffff');
      expect(BOARD_COLORS.black).toBe('#1a1a1a');
    });
  });

  describe('COLOR_CODE_MAP', () => {
    it('maps numeric codes 63-71 to colors', () => {
      expect(COLOR_CODE_MAP['63']).toBe(BOARD_COLORS.red);
      expect(COLOR_CODE_MAP['64']).toBe(BOARD_COLORS.orange);
      expect(COLOR_CODE_MAP['65']).toBe(BOARD_COLORS.yellow);
      expect(COLOR_CODE_MAP['66']).toBe(BOARD_COLORS.green);
      expect(COLOR_CODE_MAP['67']).toBe(BOARD_COLORS.blue);
      expect(COLOR_CODE_MAP['68']).toBe(BOARD_COLORS.violet);
      expect(COLOR_CODE_MAP['69']).toBe(BOARD_COLORS.white);
      expect(COLOR_CODE_MAP['70']).toBe(BOARD_COLORS.black);
    });
  });

  describe('ALL_COLOR_CODES', () => {
    it('includes both numeric and named codes', () => {
      expect(ALL_COLOR_CODES['63']).toBe(BOARD_COLORS.red);
      expect(ALL_COLOR_CODES['red']).toBe(BOARD_COLORS.red);
      expect(ALL_COLOR_CODES['purple']).toBe(BOARD_COLORS.violet); // alias
    });
  });

  describe('AVAILABLE_COLORS', () => {
    it('lists all 8 colors', () => {
      expect(AVAILABLE_COLORS).toHaveLength(8);
      expect(AVAILABLE_COLORS).toContain('red');
      expect(AVAILABLE_COLORS).toContain('violet');
      expect(AVAILABLE_COLORS).toContain('black');
    });
  });

  describe('getBoardColor', () => {
    it('returns hex for named colors', () => {
      expect(getBoardColor('red')).toBe('#eb4034');
      expect(getBoardColor('blue')).toBe('#4a90d9');
    });

    it('returns hex for numeric codes', () => {
      expect(getBoardColor('63')).toBe('#eb4034');
      expect(getBoardColor('67')).toBe('#4a90d9');
    });

    it('is case-insensitive', () => {
      expect(getBoardColor('RED')).toBe('#eb4034');
      expect(getBoardColor('Blue')).toBe('#4a90d9');
    });

    it('returns black for unknown values', () => {
      expect(getBoardColor('unknown')).toBe('#1a1a1a');
      expect(getBoardColor('999')).toBe('#1a1a1a');
    });
  });

  describe('isValidBoardColor', () => {
    it('returns true for valid colors', () => {
      expect(isValidBoardColor('red')).toBe(true);
      expect(isValidBoardColor('63')).toBe(true);
      expect(isValidBoardColor('purple')).toBe(true);
    });

    it('returns false for invalid colors', () => {
      expect(isValidBoardColor('pink')).toBe(false);
      expect(isValidBoardColor('999')).toBe(false);
    });
  });
});
