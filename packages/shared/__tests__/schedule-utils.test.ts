import { describe, it, expect } from 'vitest';
import {
  getPageColor,
  getPageColorLight,
  formatDayPattern,
  extractTimeFromDate,
  getDayNameFromDate,
  getCurrentWeekStart,
} from '../src/schedule-utils';
import type { ScheduleEntry } from '../src/api-types';

const makeSchedule = (overrides: Partial<ScheduleEntry> = {}): ScheduleEntry => ({
  id: 'sched-1',
  page_id: 'page-1',
  start_time: '09:00',
  end_time: '17:00',
  day_pattern: 'all',
  enabled: true,
  created_at: '2025-01-01T00:00:00Z',
  ...overrides,
});

describe('schedule-utils', () => {
  describe('getPageColor', () => {
    it('returns a CSS variable string', () => {
      const color = getPageColor('page-1');
      expect(typeof color).toBe('string');
      expect(color).toMatch(/^var\(--schedule-color-\d+\)$/);
    });

    it('returns consistent colors for the same ID', () => {
      const color1 = getPageColor('test-id');
      const color2 = getPageColor('test-id');
      expect(color1).toBe(color2);
    });

    it('returns different colors for different IDs', () => {
      // Not guaranteed but very likely
      const ids = ['page-1', 'page-2', 'page-3', 'page-4', 'page-5'];
      const unique = new Set(ids.map(getPageColor));
      expect(unique.size).toBeGreaterThan(1);
    });
  });

  describe('getPageColorLight', () => {
    it('returns a lighter version of the color', () => {
      const light = getPageColorLight('page-1');
      expect(typeof light).toBe('string');
    });
  });

  describe('formatDayPattern', () => {
    it('formats "all" pattern', () => {
      expect(formatDayPattern(makeSchedule({ day_pattern: 'all' }))).toBe('Every day');
    });

    it('formats "weekdays" pattern', () => {
      const result = formatDayPattern(makeSchedule({ day_pattern: 'weekdays' }));
      expect(result).toMatch(/Mon|Weekday/i);
    });

    it('formats "weekends" pattern', () => {
      const result = formatDayPattern(makeSchedule({ day_pattern: 'weekends' }));
      expect(result).toMatch(/Sat|Weekend/i);
    });

    it('formats "custom" pattern with specific days', () => {
      const result = formatDayPattern(makeSchedule({
        day_pattern: 'custom',
        custom_days: ['monday', 'wednesday', 'friday'],
      }));
      expect(typeof result).toBe('string');
      expect(result.length).toBeGreaterThan(0);
    });
  });

  describe('extractTimeFromDate', () => {
    it('extracts HH:MM from a Date', () => {
      const date = new Date(2025, 0, 15, 14, 30, 0);
      const time = extractTimeFromDate(date);
      expect(time).toBe('14:30');
    });

    it('rounds minutes to 15-minute intervals', () => {
      const date = new Date(2025, 0, 15, 9, 5, 0);
      const time = extractTimeFromDate(date);
      expect(time).toBe('09:00'); // 5 minutes rounds down to 0

      const date2 = new Date(2025, 0, 15, 14, 47, 0);
      const time2 = extractTimeFromDate(date2);
      expect(time2).toBe('14:45'); // 47 minutes rounds down to 45
    });
  });

  describe('getDayNameFromDate', () => {
    it('returns the day name', () => {
      // January 15, 2025 is a Wednesday
      const date = new Date(2025, 0, 15);
      const name = getDayNameFromDate(date);
      expect(name.toLowerCase()).toContain('wed');
    });
  });

  describe('getCurrentWeekStart', () => {
    it('returns a Date object', () => {
      const start = getCurrentWeekStart();
      expect(start).toBeInstanceOf(Date);
    });

    it('returns a Sunday', () => {
      const start = getCurrentWeekStart();
      expect(start.getDay()).toBe(0);
    });
  });
});
