/**
 * Everything this device keeps for the signed-in account, removed on sign out.
 *
 * This includes browser push enrollment, consent queries, badges and the
 * last-known board frames in IndexedDB. The service
 * worker's caches hold only the app shell and hashed build assets, which are
 * the same for every account, so they stay (the next person still gets an
 * app that opens offline, with nothing of yours in it).
 */
import type { QueryClient } from "@tanstack/react-query";

import { clearAppBadge } from "./app-badge";
import { clearLastKnownBoards } from "./last-known-board";
import { clearBrowserPush } from "./push";

/** Sign out never waits longer than this on local storage. */
export const CLEAR_TIMEOUT_MS = 1000;

export async function clearAccountDataOnDevice(queryClient?: QueryClient): Promise<void> {
  // Removing also cancels in-flight reads, so an old session cannot refill
  // the next session's consent state after logout.
  queryClient?.removeQueries({ queryKey: ["push-status"] });
  queryClient?.removeQueries({ queryKey: ["browser-push"] });
  // A wedged IndexedDB (another tab holding an upgrade, a broken profile)
  // must not trap anyone in a session they asked to leave.
  await Promise.race([
    Promise.allSettled([clearLastKnownBoards(), clearBrowserPush(), clearAppBadge()]),
    new Promise((resolve) => setTimeout(resolve, CLEAR_TIMEOUT_MS)),
  ]);
}
