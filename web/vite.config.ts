import { reactRouter } from "@react-router/dev/vite";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";
import { fileURLToPath } from "node:url";
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
 * For HA Ingress, the runtime prefix is injected by nginx's sub_filter
 * rewriting `/assets/`, `/sw.js`, `/icons/`, `/manifest.json` in both
 * HTML and JS response bodies (see entrypoint.sh::configure_ingress_path_rewrite).
 * Unlike Next.js's `<link rel="preload">` font URLs that React 19's
 * `ReactDOM.preload()` constructs at runtime from a baked-in empty
 * assetPrefix, every asset URL Vite emits lives as a string literal in
 * the build output — nginx can rewrite them all.
 *
 * Direct deployments (`X-Ingress-Path` absent) get the snippet expanded
 * to no-op substitutions and incur only the gzip-pass-through overhead.
 */
export default defineConfig({
  base: "/",
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      // Temporary compat shims so the 135 client components keep working
      // without per-file edits during the Next.js → RR7 migration. The
      // shims wrap react-router / react-i18next with next/*-shaped APIs.
      // See `src/lib/next-compat/` for implementations. These can be
      // codemodded away later — they're a permanent-OK thin layer.
      "next/navigation": path.resolve(__dirname, "./src/lib/next-compat/navigation.ts"),
      "next/link": path.resolve(__dirname, "./src/lib/next-compat/link.tsx"),
      "next/dynamic": path.resolve(__dirname, "./src/lib/next-compat/dynamic.tsx"),
      "next/image": path.resolve(__dirname, "./src/lib/next-compat/image.tsx"),
      "next-intl": path.resolve(__dirname, "./src/lib/next-compat/intl.tsx"),
    },
  },
  plugins: [
    tailwindcss(),
    reactRouter(),
    VitePWA({
      registerType: "autoUpdate",
      strategies: "generateSW",
      injectRegister: "auto",
      workbox: {
        navigateFallback: "/offline",
        // Match the Next-PWA configuration we're replacing: NetworkFirst
        // across the board with a 10s timeout and a 200-entry / 7-day
        // expiration. See the old `next.config.ts::withPWA` block.
        runtimeCaching: [
          {
            urlPattern: /^https?.*/,
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
