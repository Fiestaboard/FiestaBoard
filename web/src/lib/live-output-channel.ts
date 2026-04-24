/**
 * Cross-tab broadcast channel for Live Output state.
 *
 * The page builder writes the current live message here; the home screen
 * (active-page-display) reads it. Within a single tab, the React Query cache
 * provides instant reactivity. Across tabs, we use localStorage so that a
 * `storage` event fires in other tabs.
 *
 * Key: "fiestaboard:liveOutputMessage"
 * Value: JSON-encoded string | null
 */

const STORAGE_KEY = "fiestaboard:liveOutputMessage";

/** Write a live message (or null to clear) to localStorage so other tabs pick it up. */
export function writeLiveOutputMessage(message: string | null): void {
  try {
    if (message === null) {
      localStorage.removeItem(STORAGE_KEY);
    } else {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(message));
    }
  } catch {
    // localStorage may be unavailable (private mode, storage quota, etc.)
  }
}

/** Read the current live message from localStorage (null if not set). */
export function readLiveOutputMessage(): string | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === null) return null;
    return JSON.parse(raw) as string;
  } catch {
    return null;
  }
}

/**
 * Subscribe to live output message changes from other tabs.
 * Returns an unsubscribe function.
 */
export function onLiveOutputMessageChange(
  callback: (message: string | null) => void
): () => void {
  const handler = (event: StorageEvent) => {
    if (event.key !== STORAGE_KEY) return;
    if (event.newValue === null) {
      callback(null);
    } else {
      try {
        callback(JSON.parse(event.newValue) as string);
      } catch {
        callback(null);
      }
    }
  };
  window.addEventListener("storage", handler);
  return () => window.removeEventListener("storage", handler);
}
