import path from "node:path";
import { fileURLToPath } from "node:url";

import { reactRouter } from "@react-router/dev/vite";
import tailwindcss from "@tailwindcss/vite";
import { visualizer } from "rollup-plugin-visualizer";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

// `__dirname` isn't defined in ESM; package.json sets `"type": "module"`.
const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Vite config for the React Router v7 framework-mode build.
 *
 * `base: "/"` (absolute) is required because ES dynamic `import()` calls
 * inside lazy route chunks resolve relative to the importing module's
 * URL — NOT the document `<base href>`. With `base: "./"`, a chunk
 * loaded from `/assets/index-X.js` would dynamic-import `./assets/foo.js`
 * which resolves to `/assets/assets/foo.js` (double prefix) → 404.
 *
 * For HA Ingress, the runtime prefix is applied in two complementary ways:
 *
 * 1. HTML and CSS bodies: nginx sub_filter rewrites `/assets/`, `/sw.js`,
 *    `/icons/`, `/manifest.json` literals at request time
 *    (see entrypoint.sh::configure_ingress_path_rewrite).
 *
 * 2. JS-hosted asset references: `experimental.renderBuiltUrl` below.
 *    Since the Vite 8 (rolldown) toolchain, chunk URLs no longer exist as
 *    `"/assets/..."` string literals in the JS output — `__vite__mapDeps`
 *    stores RELATIVE `"assets/..."` strings and the preload helper
 *    concatenates the base at runtime (`assetsURL = f => "/" + f`), and the
 *    oxc minifier emits backtick-quoted strings sub_filter patterns don't
 *    match. Both make body rewriting unreliable for JS, so JS-hosted URLs
 *    are instead routed through `window.__fbAssetUrl`, a classic-script
 *    global defined in app/root.tsx that prepends the React Router
 *    basename (the same source of truth src/lib/base-path.ts uses for
 *    API URLs).
 *
 * Direct deployments (`X-Ingress-Path` absent) keep basename "/" so the
 * runtime helper degrades to the plain absolute path, and the sub_filter
 * snippet expands to no-op substitutions.
 */
export default defineConfig({
  base: "/",
  experimental: {
    renderBuiltUrl(filename, { hostType }) {
      if (hostType === "js") {
        // SSR/prerender never loads assets through this expression, but
        // guard on `window` anyway so evaluating it outside a browser
        // (e.g. jsdom without the root.tsx inline script) still yields a
        // usable root-absolute URL.
        const file = JSON.stringify(filename);
        return {
          runtime: `typeof window!=="undefined"&&window.__fbAssetUrl?window.__fbAssetUrl(${file}):"/"+${file}`,
        };
      }
      // HTML and CSS keep the default absolute `base: "/"` emission,
      // which nginx sub_filter rewrites under HA Ingress.
      return undefined;
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  plugins: [
    tailwindcss(),
    // `@vitejs/plugin-react` is intentionally NOT used here. Including
    // it conflicts with RR7's own React Refresh integration: plugin-react
    // injects `import RefreshRuntime from "/@react-refresh"` into every
    // React module, and `@react-router/dev/vite`'s transform injects
    // the same name from its own HMR runtime — the two collide with
    // "Cannot declare an imported binding name twice: 'RefreshRuntime'".
    // RR7 handles Fast Refresh itself; we just need to satisfy its
    // preamble check, which `app/root.tsx::DEV_REACT_REFRESH_PREAMBLE`
    // does by setting `window.__vite_plugin_react_preamble_installed__`
    // inline in Layout's `<head>` before the route module imports.
    reactRouter(),
    VitePWA({
      registerType: "autoUpdate",
      strategies: "generateSW",
      injectRegister: "auto",
      workbox: {
        navigateFallback: "/offline",
        // A new SW that ships in a deploy takes over immediately
        // instead of waiting for every controlled tab to close
        // (otherwise users on long-lived tabs stay on the old build
        // until they fully quit the app). cleanupOutdatedCaches sheds
        // precaches from prior workbox revisions so storage doesn't
        // accumulate stale assets.
        skipWaiting: true,
        clientsClaim: true,
        cleanupOutdatedCaches: true,
        // NetworkFirst with a 10s timeout and a 200-entry / 7-day
        // expiration for everything EXCEPT top-level navigation HTML.
        // Caching the document under NetworkFirst means a transient
        // slow network (>10s) serves a stale index.html whose hashed
        // /assets/<old>.js chunks may not exist in the current build
        // → white screen until a hard refresh. The document is already
        // covered by precache + navigateFallback for the offline case,
        // so the safe move is to keep it out of this runtime cache and
        // always go to the network for navigations.
        runtimeCaching: [
          {
            urlPattern: ({ request }) => request.destination !== "document",
            handler: "NetworkFirst",
            options: {
              cacheName: "offlineCache",
              expiration: {
                maxEntries: 200,
                maxAgeSeconds: 60 * 60 * 24 * 7,
              },
              networkTimeoutSeconds: 10,
            },
          },
        ],
      },
      // We ship our own /public/manifest.json — don't let the plugin
      // generate or overwrite it.
      manifest: false,
      includeAssets: ["favicon.ico", "icons/*.png", "manifest.json"],
      devOptions: { enabled: false },
    }),
    process.env.ANALYZE === "true" &&
      (visualizer({
        open: false,
        filename: "build/bundle-analysis.html",
        gzipSize: true,
        brotliSize: true,
      }) as unknown as ReturnType<typeof reactRouter>[number]),
  ].filter(Boolean) as ReturnType<typeof reactRouter>,
  server: {
    port: 3001,
    host: "127.0.0.1",
    strictPort: true,
    // In dev, the FastAPI backend runs at 127.0.0.1:8000 (supervisord-dev).
    // Proxy /api/* through Vite so the dev server matches the production
    // nginx layout. Production traffic does NOT go through this proxy —
    // it goes through nginx (see nginx.conf).
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
  build: {
    sourcemap: true,
  },
});
