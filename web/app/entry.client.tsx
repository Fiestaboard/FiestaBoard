/**
 * Client entry point for the React Router v7 build.
 *
 * Runs once on first load. Responsibilities:
 *  1. Initialize i18next via the side-effect import.
 *  2. Hydrate the React Router app.
 *
 * Service worker lifecycle is handled by vite-plugin-pwa's auto-injected
 * register script (`injectRegister: "auto"` in vite.config.ts) plus the
 * workbox `skipWaiting` / `clientsClaim` config — no manual SW management
 * is needed here.
 */
import "@/i18n/i18next";

import { startTransition, StrictMode } from "react";
import { hydrateRoot } from "react-dom/client";
import { HydratedRouter } from "react-router/dom";

startTransition(() => {
  hydrateRoot(
    document,
    <StrictMode>
      <HydratedRouter />
    </StrictMode>,
  );
});
