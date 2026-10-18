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
    // The service worker is retired. Since the React Router migration (#919)
    // the plugin wrote sw.js to `dist/`, which nothing serves, so /sw.js
    // 404'd on every load and the app never had a working one. A real one
    // buys no speed here (hashed /assets/ are already `immutable` for a year)
    // and would re-download the whole bundle after every nightly update.
    // `selfDestroying` ships a sw.js that unregisters itself and clears its
    // caches, which also evicts any Next.js-era worker still controlling a
    // long-lived tab with a stale precache. Once those are gone (a few
    // releases), this plugin and public/registerSW references can go too.
    VitePWA({
      selfDestroying: true,
      injectRegister: "auto",
      // React Router's client build dir; the plugin's default (`dist/`) is
      // never served.
      outDir: "build/client",
      // We ship our own /public/manifest.json — don't let the plugin
      // generate or overwrite it.
      manifest: false,
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
    // Emitted for debugging builds locally, but without the
    // `sourceMappingURL` comment, and nginx refuses to serve *.map: a
    // production instance should not hand its full source to any visitor.
    sourcemap: "hidden",
  },
});
