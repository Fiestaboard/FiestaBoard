import { describe, it, expect } from 'vitest';
import {
  DEVICE_DIMENSIONS,
  BOARD_WIDTH,
  BOARD_LINES,
  BOARD_COLOR_CODES,
  BOARD_CHARS,
  COLOR_TILE_CODES,
  FILL_SPACE_VAR,
  FILL_SPACE_REPEAT_VAR,
} from '../src/board-constants';

describe('board-constants', () => {
  describe('DEVICE_DIMENSIONS', () => {
    it('defines flagship as 6x22', () => {
      expect(DEVICE_DIMENSIONS.flagship).toEqual({ rows: 6, cols: 22 });
    });

    it('defines note as 3x15', () => {
      expect(DEVICE_DIMENSIONS.note).toEqual({ rows: 3, cols: 15 });
    });
  });

  describe('BOARD_WIDTH and BOARD_LINES', () => {
    it('defaults to flagship dimensions', () => {
      expect(BOARD_WIDTH).toBe(22);
      expect(BOARD_LINES).toBe(6);
    });
  });

  describe('BOARD_COLOR_CODES', () => {
    it('maps color names to hardware codes 63-70', () => {
      expect(BOARD_COLOR_CODES.red).toBe(63);
      expect(BOARD_COLOR_CODES.orange).toBe(64);
      expect(BOARD_COLOR_CODES.yellow).toBe(65);
      expect(BOARD_COLOR_CODES.green).toBe(66);
      expect(BOARD_COLOR_CODES.blue).toBe(67);
      expect(BOARD_COLOR_CODES.violet).toBe(68);
      expect(BOARD_COLOR_CODES.white).toBe(69);
      expect(BOARD_COLOR_CODES.black).toBe(70);
    });

    it('has purple as alias for violet', () => {
      expect(BOARD_COLOR_CODES.purple).toBe(BOARD_COLOR_CODES.violet);
    });
  });

  describe('BOARD_CHARS', () => {
    it('has 72 entries (codes 0-71)', () => {
      expect(BOARD_CHARS).toHaveLength(72);
    });

    it('maps code 0 to blank space', () => {
      expect(BOARD_CHARS[0]).toBe(' ');
    });

    it('maps codes 1-26 to A-Z', () => {
      expect(BOARD_CHARS[1]).toBe('A');
      expect(BOARD_CHARS[26]).toBe('Z');
    });

    it('maps codes 27-36 to digits 1-9, 0', () => {
      expect(BOARD_CHARS[27]).toBe('1');
      expect(BOARD_CHARS[35]).toBe('9');
      expect(BOARD_CHARS[36]).toBe('0');
    });

    it('maps codes 63-71 to color tile strings', () => {
      expect(BOARD_CHARS[63]).toBe('63');
      expect(BOARD_CHARS[70]).toBe('70');
      expect(BOARD_CHARS[71]).toBe('71');
    });
  });

  describe('COLOR_TILE_CODES', () => {
    it('contains codes 63-71', () => {
      expect(COLOR_TILE_CODES.has('63')).toBe(true);
      expect(COLOR_TILE_CODES.has('71')).toBe(true);
      expect(COLOR_TILE_CODES.has('62')).toBe(false);
      expect(COLOR_TILE_CODES.has('72')).toBe(false);
    });

    it('has exactly 9 entries', () => {
      expect(COLOR_TILE_CODES.size).toBe(9);
    });
  });

  describe('template variable names', () => {
    it('defines fill space variables', () => {
      expect(FILL_SPACE_VAR).toBe('fill_space');
      expect(FILL_SPACE_REPEAT_VAR).toBe('fill_space_repeat');
    });
  });
});
