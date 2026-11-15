/**
 * Registers the app-shell service worker (WEB-16), only where one can run.
 *
 * - Secure contexts only. On plain http there is no `navigator.serviceWorker`
 *   at all, and the app says "needs HTTPS" instead of pretending.
 * - The URL and scope come from `appUrl`, so under HA Ingress the worker is
 *   `<ingress>/sw.js` with scope `<ingress>/`, never the host root.
 * - `updateViaCache: "none"`: the browser re-fetches sw.js and its imported
 *   policy on every check, so a new release's worker is never held back by
 *   the HTTP cache.
 */
import { appUrl } from "@/lib/base-path";

import { isSecureOrigin } from "./environment";

export async function registerServiceWorker(
  win: Pick<Window, "isSecureContext"> & { navigator: Partial<Pick<Navigator, "serviceWorker">> } = window,
): Promise<ServiceWorkerRegistration | null> {
  if (!isSecureOrigin(win)) return null;
  const container = win.navigator.serviceWorker;
  if (!container) return null;
  try {
    return await container.register(appUrl("/sw.js"), { scope: appUrl("/"), updateViaCache: "none" });
  } catch {
    // A failed registration leaves the app working online, as before.
    return null;
  }
}
