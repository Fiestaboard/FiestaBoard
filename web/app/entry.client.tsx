/**
 * Client entry point for the React Router v7 build.
 *
 * Runs once on first load. Responsibilities:
 *  1. Initialize i18next and wait for the visitor's locale chunk (English
 *     is bundled, so for most visitors this resolves immediately).
 *  2. Hydrate the React Router app.
 *
 * There is no service worker: vite-plugin-pwa ships a self-destroying
 * sw.js that removes any previously installed one (see vite.config.ts).
 */
import { startTransition, StrictMode } from "react";
import { hydrateRoot } from "react-dom/client";
import { HydratedRouter } from "react-router/dom";

import { i18nReady } from "@/i18n/i18next";

function hydrate() {
  startTransition(() => {
    hydrateRoot(
      document,
      <StrictMode>
        <HydratedRouter />
      </StrictMode>,
    );
  });
}

// A failed locale fetch falls back to English rather than blocking the app.
i18nReady.then(hydrate, hydrate);
