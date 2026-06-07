/**
 * Client entry point for the React Router v7 build.
 *
 * Runs once on first load. Responsibilities:
 *  1. Unregister any stale service workers from the previous Next-PWA
 *     deployment (kill-switch) so users don't get cached `/_next/*`
 *     responses after the cutover. This is a one-time cost per user.
 *  2. Initialize i18next via the side-effect import.
 *  3. Hydrate the React Router app.
 */
import "@/i18n/i18next";

import { startTransition, StrictMode } from "react";
import { hydrateRoot } from "react-dom/client";
import { HydratedRouter } from "react-router/dom";

const KILL_SWITCH_FLAG = "fiestaboard:sw-killed:v1";
const NEW_SW_MARKER = "fiestaboard-vite-pwa";

async function killStaleServiceWorkers(): Promise<boolean> {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
    return false;
  }
  try {
    const regs = await navigator.serviceWorker.getRegistrations();
    const stale = regs.filter((r) => {
      // The new Vite-PWA service worker is tagged with NEW_SW_MARKER in
      // its scriptURL or scope (see vite-plugin-pwa config). Anything
      // else is from the previous Next-PWA install and must go.
      const url = r.active?.scriptURL ?? r.installing?.scriptURL ?? r.waiting?.scriptURL ?? "";
      return !url.includes(NEW_SW_MARKER);
    });
    if (stale.length === 0) return false;
    await Promise.all(stale.map((r) => r.unregister()));
    if (typeof caches !== "undefined") {
      try {
        const keys = await caches.keys();
        await Promise.all(keys.map((k) => caches.delete(k)));
      } catch {
        /* ignore */
      }
    }
    return true;
  } catch {
    return false;
  }
}

async function boot() {
  if (!sessionStorage.getItem(KILL_SWITCH_FLAG)) {
    const killed = await killStaleServiceWorkers();
    if (killed) {
      sessionStorage.setItem(KILL_SWITCH_FLAG, "1");
      window.location.reload();
      return;
    }
    sessionStorage.setItem(KILL_SWITCH_FLAG, "1");
  }

  startTransition(() => {
    hydrateRoot(
      document,
      <StrictMode>
        <HydratedRouter />
      </StrictMode>,
    );
  });
}

void boot();
