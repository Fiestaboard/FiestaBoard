/**
 * Asks the Creator IDE to show its Problems list, from outside the IDE (the
 * preview's Missing panel, UX-4-4), without a handle on the page builder: the
 * IDE listens for this event and opens Problems the way its own status-line
 * link does.
 */
export const OPEN_PROBLEMS_EVENT = "fiestaboard:ide-open-problems";

export function openIdeProblems(): void {
  window.dispatchEvent(new Event(OPEN_PROBLEMS_EVENT));
}
