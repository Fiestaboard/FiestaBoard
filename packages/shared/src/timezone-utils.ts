/**
 * Timezone conversion utilities for handling UTC <-> local time conversions.
 *
 * Uses date-fns-tz for reliable timezone conversions.
 */

import { format, parseISO } from 'date-fns';
import { formatInTimeZone, toZonedTime, fromZonedTime, getTimezoneOffset as getDateFnsTimezoneOffset } from 'date-fns-tz';

/**
 * Convert local time (HH:MM) to UTC ISO format
 *
 * @param localTime - Time in HH:MM format (e.g., "20:00")
 * @param timezone - IANA timezone name (e.g., "America/Los_Angeles")
 * @returns UTC time in ISO format (e.g., "04:00+00:00")
 */
export function localTimeToUTC(localTime: string, timezone: string): string {
  try {
    // Parse local time
    const [hours, minutes] = localTime.split(':').map(Number);

    // Validate parsed values
    if (isNaN(hours) || isNaN(minutes)) {
      console.error('Error converting local time to UTC: Invalid time format');
      return '00:00+00:00';
    }

    // Create a date object for today at this time in the specified timezone
    const now = new Date();
    const localDate = new Date(now.getFullYear(), now.getMonth(), now.getDate(), hours, minutes);

    // Convert to UTC
    const utcDate = fromZonedTime(localDate, timezone);

    // Format as HH:MM+00:00
    const utcHours = utcDate.getUTCHours();
    const utcMinutes = utcDate.getUTCMinutes();

    // Check for NaN after conversion
    if (isNaN(utcHours) || isNaN(utcMinutes)) {
      console.error('Error converting local time to UTC: Invalid result');
      return '00:00+00:00';
    }

    return `${utcHours.toString().padStart(2, '0')}:${utcMinutes.toString().padStart(2, '0')}+00:00`;
  } catch (error) {
    console.error('Error converting local time to UTC:', error);
    return '00:00+00:00';
  }
}

/**
 * Convert UTC ISO time to local time
 *
 * @param utcIso - UTC time in ISO format (e.g., "04:00+00:00")
 * @param timezone - IANA timezone name (e.g., "America/Los_Angeles")
 * @returns Local time in HH:MM format (e.g., "20:00")
 */
export function utcToLocalTime(utcIso: string, timezone: string): string {
  try {
    // Parse UTC time (format: HH:MM+00:00)
    const timePart = utcIso.split('+')[0].split('-')[0]; // Get HH:MM part
    const [hours, minutes] = timePart.split(':').map(Number);

    // Validate parsed values
    if (isNaN(hours) || isNaN(minutes)) {
      console.error('Error converting UTC to local time: Invalid time format');
      return '00:00';
    }

    // Create a UTC date object for today at this time
    const now = new Date();
    const utcDate = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), hours, minutes));

    // Convert to target timezone
    const localDate = toZonedTime(utcDate, timezone);

    // Format as HH:MM
    const localHours = localDate.getHours();
    const localMinutes = localDate.getMinutes();

    // Check for NaN after conversion
    if (isNaN(localHours) || isNaN(localMinutes)) {
      console.error('Error converting UTC to local time: Invalid result');
      return '00:00';
    }

    return `${localHours.toString().padStart(2, '0')}:${localMinutes.toString().padStart(2, '0')}`;
  } catch (error) {
    console.error('Error converting UTC to local time:', error);
    return '00:00';
  }
}

/**
 * Format a UTC timestamp for display in the user's timezone
 *
 * @param utcTimestamp - ISO 8601 timestamp in UTC (e.g., "2025-12-26T22:30:00+00:00")
 * @param timezone - IANA timezone name for display
 * @param formatStr - Optional format string (defaults to "yyyy-MM-dd HH:mm:ss zzz")
 * @returns Formatted timestamp string in local timezone
 */
export function formatTimestampLocal(
  utcTimestamp: string,
  timezone: string,
  formatStr: string = 'yyyy-MM-dd HH:mm:ss zzz'
): string {
  try {
    // Parse the UTC timestamp
    const date = parseISO(utcTimestamp);

    // Format in the target timezone
    return formatInTimeZone(date, timezone, formatStr);
  } catch (error) {
    console.error('Error formatting timestamp:', error);
    return utcTimestamp;
  }
}

/**
 * Format a log timestamp for display (shorter format)
 *
 * @param utcTimestamp - ISO 8601 timestamp in UTC
 * @param timezone - IANA timezone name for display
 * @returns Formatted timestamp like "14:30:45" (time only)
 */
export function formatLogTimestamp(utcTimestamp: string, timezone: string): string {
  return formatTimestampLocal(utcTimestamp, timezone, 'HH:mm:ss');
}

/**
 * Format a log timestamp with full date for tooltips
 *
 * @param utcTimestamp - ISO 8601 timestamp in UTC
 * @param timezone - IANA timezone name for display
 * @returns Formatted timestamp like "Dec 26, 2025 2:30:45 PM PST"
 */
export function formatLogTimestampFull(utcTimestamp: string, timezone: string): string {
  return formatTimestampLocal(utcTimestamp, timezone, 'MMM dd, yyyy h:mm:ss a zzz');
}

/**
 * Get the timezone abbreviation for display
 *
 * @param timezone - IANA timezone name
 * @returns Timezone abbreviation (e.g., "PST", "EST")
 */
export function getTimezoneAbbreviation(timezone: string): string {
  try {
    const now = new Date();
    return formatInTimeZone(now, timezone, 'zzz');
  } catch (error) {
    console.error('Error getting timezone abbreviation:', error);
    return timezone;
  }
}

/**
 * Get UTC offset string for a timezone (e.g., "UTC-8", "UTC+5:30")
 */
export function getTimezoneOffsetString(timezone: string): string {
  try {
    const now = new Date();
    const offsetMs = getDateFnsTimezoneOffset(timezone, now);
    const offsetMinutes = offsetMs / (1000 * 60);
    const hours = Math.floor(Math.abs(offsetMinutes) / 60);
    const minutes = Math.abs(offsetMinutes) % 60;
    const sign = offsetMinutes >= 0 ? '+' : '-';

    if (minutes === 0) {
      return `UTC${sign}${hours}`;
    }
    return `UTC${sign}${hours}:${minutes.toString().padStart(2, '0')}`;
  } catch {
    return 'UTC';
  }
}

/**
 * All IANA timezones with their current UTC offsets
 */
export const ALL_TIMEZONES = [
  // UTC
  'UTC',
  // Americas
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Anchorage',
  'America/Phoenix',
  'America/Toronto',
  'America/Vancouver',
  'America/Edmonton',
  'America/Winnipeg',
  'America/Halifax',
  'America/St_Johns',
  'America/Mexico_City',
  'America/Cancun',
  'America/Monterrey',
  'America/Guatemala',
  'America/El_Salvador',
  'America/Costa_Rica',
  'America/Panama',
  'America/Bogota',
  'America/Lima',
  'America/Santiago',
  'America/Buenos_Aires',
  'America/Sao_Paulo',
  'America/Rio_de_Janeiro',
  'America/Caracas',
  'America/La_Paz',
  'America/Guyana',
  'America/Montevideo',
  'America/Godthab',
  'Pacific/Honolulu',
  // Europe
  'Europe/London',
  'Europe/Dublin',
  'Europe/Lisbon',
  'Europe/Paris',
  'Europe/Madrid',
  'Europe/Barcelona',
  'Europe/Berlin',
  'Europe/Frankfurt',
  'Europe/Munich',
  'Europe/Rome',
  'Europe/Milan',
  'Europe/Vienna',
  'Europe/Zurich',
  'Europe/Amsterdam',
  'Europe/Brussels',
  'Europe/Copenhagen',
  'Europe/Stockholm',
  'Europe/Oslo',
  'Europe/Helsinki',
  'Europe/Warsaw',
  'Europe/Prague',
  'Europe/Budapest',
  'Europe/Athens',
  'Europe/Bucharest',
  'Europe/Sofia',
  'Europe/Istanbul',
  'Europe/Kiev',
  'Europe/Moscow',
  'Europe/Minsk',
  // Asia
  'Asia/Dubai',
  'Asia/Muscat',
  'Asia/Baku',
  'Asia/Tbilisi',
  'Asia/Yerevan',
  'Asia/Kabul',
  'Asia/Karachi',
  'Asia/Tashkent',
  'Asia/Kolkata',
  'Asia/Mumbai',
  'Asia/Delhi',
  'Asia/Colombo',
  'Asia/Kathmandu',
  'Asia/Dhaka',
  'Asia/Almaty',
  'Asia/Yangon',
  'Asia/Bangkok',
  'Asia/Jakarta',
  'Asia/Ho_Chi_Minh',
  'Asia/Shanghai',
  'Asia/Hong_Kong',
  'Asia/Taipei',
  'Asia/Singapore',
  'Asia/Kuala_Lumpur',
  'Asia/Manila',
  'Asia/Tokyo',
  'Asia/Seoul',
  'Asia/Pyongyang',
  'Asia/Jerusalem',
  'Asia/Beirut',
  'Asia/Amman',
  'Asia/Damascus',
  'Asia/Baghdad',
  'Asia/Riyadh',
  'Asia/Kuwait',
  'Asia/Tehran',
  // Africa
  'Africa/Cairo',
  'Africa/Johannesburg',
  'Africa/Nairobi',
  'Africa/Lagos',
  'Africa/Algiers',
  'Africa/Casablanca',
  'Africa/Tunis',
  'Africa/Accra',
  'Africa/Addis_Ababa',
  'Africa/Dar_es_Salaam',
  'Africa/Khartoum',
  'Africa/Tripoli',
  // Australia & Pacific
  'Australia/Sydney',
  'Australia/Melbourne',
  'Australia/Brisbane',
  'Australia/Perth',
  'Australia/Adelaide',
  'Australia/Darwin',
  'Pacific/Auckland',
  'Pacific/Fiji',
  'Pacific/Guam',
  'Pacific/Port_Moresby',
  'Pacific/Noumea',
  'Pacific/Tongatapu',
  'Pacific/Apia',
  'Pacific/Tahiti',
  'Pacific/Pago_Pago',
  'Pacific/Midway',
].map((tz) => ({
  value: tz,
  label: `${tz.replace(/_/g, ' ')} (${getTimezoneOffsetString(tz)})`,
  offset: getTimezoneOffsetString(tz),
})).sort((a, b) => {
  // Sort by offset first (UTC+X), then by name
  const getOffsetValue = (offset: string) => {
    if (offset === 'UTC') return 0;
    const match = offset.match(/UTC([+-])(\d+)(?::(\d+))?/);
    if (!match) return 0;
    const hours = parseInt(match[2]);
    const minutes = parseInt(match[3] || '0');
    const totalMinutes = hours * 60 + minutes;
    return match[1] === '+' ? totalMinutes : -totalMinutes;
  };

  const offsetDiff = getOffsetValue(a.offset) - getOffsetValue(b.offset);
  if (offsetDiff !== 0) return offsetDiff;
  return a.value.localeCompare(b.value);
});

// Keep COMMON_TIMEZONES as an alias for backwards compatibility
export const COMMON_TIMEZONES = ALL_TIMEZONES;
