/**
 * FiestaPanel's night-time auto-dim: the window, and how dark it goes.
 * Shared by the viewer on the TV (its overlay) and the app's preview of it
 * (`TvFrame`'s `dimmed`), so both show the same screen.
 */

/** The viewer's overlay opacity inside the dim window (0 = none, 1 = black). */
export const PANEL_DIM_LEVEL = 0.65;

/**
 * Whether `minutesSinceMidnight` falls inside the [start, end) dim window.
 * `start > end` means the window spans midnight (e.g. 22:00 → 07:00).
 * `start === end` never dims.
 */
export function isInDimWindow(minutesSinceMidnight: number, start: string, end: string): boolean {
  const toMinutes = (hhmm: string) => {
    const [h, m] = hhmm.split(":").map(Number);
    return h * 60 + m;
  };
  const startMin = toMinutes(start);
  const endMin = toMinutes(end);
  if (startMin === endMin) return false;
  if (startMin < endMin) return minutesSinceMidnight >= startMin && minutesSinceMidnight < endMin;
  return minutesSinceMidnight >= startMin || minutesSinceMidnight < endMin;
}
