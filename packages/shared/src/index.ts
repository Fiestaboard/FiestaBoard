/**
 * @fiestaboard/shared
 * Platform-agnostic code shared between web and mobile apps.
 */

// API types (primary source of truth for all API-related types)
export * from './api-types';

// API client factory
export { createApiClient } from './api-client';
export type { ApiClient } from './api-client';

// Board color utilities
export * from './board-colors';

// Board hardware constants (DeviceType re-exported from api-types via board-constants)
export {
  DEVICE_DIMENSIONS,
  BOARD_WIDTH,
  BOARD_LINES,
  BOARD_COLOR_CODES,
  BOARD_CHARS,
  COLOR_TILE_CODES,
  FILL_SPACE_VAR,
  FILL_SPACE_REPEAT_VAR,
} from './board-constants';
export type { DeviceDimensions, BoardColorCodeName } from './board-constants';

// Schedule utilities
export {
  schedulesToCalendarEvents,
  scheduleToCalendarEvents,
  extractTimeFromDate,
  getPageColor,
  getPageColorLight,
  formatDayPattern,
  getCurrentWeekStart,
  formatWeekRange,
  isEventOnDay,
  getDayNameFromDate,
} from './schedule-utils';
export type { CalendarEvent } from './schedule-utils';

// Timezone utilities
export {
  localTimeToUTC,
  utcToLocalTime,
  formatTimestampLocal,
  formatLogTimestamp,
  formatLogTimestampFull,
  getTimezoneAbbreviation,
  getTimezoneOffsetString,
  ALL_TIMEZONES,
  COMMON_TIMEZONES,
} from './timezone-utils';
