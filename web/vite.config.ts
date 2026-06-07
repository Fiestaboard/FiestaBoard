import { reactRouter } from "@react-router/dev/vite";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";
import { visualizer } from "rollup-plugin-visualizer";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

/**
 * Vite config for the React Router v7 framework-mode build.
 *
 * Critical choice: `base: "./"` emits relative asset URLs so the browser
 * resolves them against `<base href>`. nginx injects `<base href>` from
 * `X-Ingress-Path` at request time, which is how HA Supervisor Ingress
 * subpaths work without any prototype patching or sub_filter of asset
 * URLs. Direct deployments get `<base href="/">` (identity).
 *
 * The Next.js → RR7 migration intentionally moves away from build-time
 * `assetPrefix` because there is no runtime equivalent in Next.js. See
 * the `<base href>` snippet in `entrypoint.sh::configure_ingress_path_rewrite`
 * for the nginx side.
 */
export default defineConfig({
  base: "./",
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
