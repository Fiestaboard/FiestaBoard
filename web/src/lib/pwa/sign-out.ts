/**
 * Everything this device keeps for the signed-in account, removed on sign out.
 *
 * Today that is the last-known board frames in IndexedDB. The service
 * worker's caches hold only the app shell and hashed build assets, which are
 * the same for every account, so they stay (the next person still gets an
 * app that opens offline, with nothing of yours in it).
 */
import { clearLastKnownBoards } from "./last-known-board";

/** Sign out never waits longer than this on local storage. */
export const CLEAR_TIMEOUT_MS = 1000;

export async function clearAccountDataOnDevice(): Promise<void> {
  // A wedged IndexedDB (another tab holding an upgrade, a broken profile)
  // must not trap anyone in a session they asked to leave.
  await Promise.race([clearLastKnownBoards(), new Promise((resolve) => setTimeout(resolve, CLEAR_TIMEOUT_MS))]);
}
