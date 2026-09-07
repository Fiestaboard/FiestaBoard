import type { Config } from "@react-router/dev/config";

/**
 * React Router v7 framework-mode config.
 *
 * `ssr: false` — produces a static SPA build under `build/client/`. No Node
 * runtime in production; nginx serves the static files directly. This is
 * the key choice that lets HA Ingress work: nginx sub_filter rewrites the
 * build's absolute URL literals (and the inlined `"basename":"/"` hydration
 * value, which the SPA reads back to prefix API calls — see
 * src/lib/base-path.ts) at request time, instead of fighting Next.js's
 * build-time assetPrefix.
 *
 * `appDirectory` defaults to `app/`; files there become route modules via
 * `app/routes.ts`.
 */
export default {
  ssr: false,
  appDirectory: "app",
} satisfies Config;
