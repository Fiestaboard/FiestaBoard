// Runtime base-path detection for reverse-proxy subpath deployments
// (HA Ingress). The add-on's nginx rewrites the SPA's inlined
// `"basename":"/"` hydration literal to `"basename":"<prefix>/"`
// (entrypoint.sh::configure_ingress_path_rewrite), so React Router's
// hydration global is the single source of truth for the prefix.
// Direct deployments keep basename "/" -> base path "".
//
// Read lazily per call: the global is inlined as a classic <script>
// ahead of the deferred module bundle in production, but is absent in
// `vite dev` and jsdom tests, where the helper degrades to "".
//
// IMPORTANT: never write a string literal matching `"/api/` (with the
// trailing slash) in this module or its callers — nginx sub_filter
// still rewrites that pattern in JS bodies as a fallback and would
// prefix such a literal a second time.

interface ReactRouterContextGlobal {
  __reactRouterContext?: { basename?: string };
}

/** "" for direct deployments; "/api/hassio_ingress/<token>" under HA Ingress. */
export function getBasePath(): string {
  if (typeof window === "undefined") return "";
  const basename = (window as unknown as ReactRouterContextGlobal).__reactRouterContext?.basename;
  if (!basename || basename === "/") return "";
  return basename.replace(/\/+$/, "");
}

/** Build an API URL: apiUrl("/health") -> "/api/health" or "<prefix>/api/health". */
export function apiUrl(path: string): string {
  return `${getBasePath()}/api${path}`;
}

/**
 * Build a document URL for hard navigations (window.location.assign),
 * which bypass React Router's basename handling: appUrl("/login") ->
 * "/login" or "<prefix>/login". Router-based navigation (router.push,
 * <Link>) must NOT use this — the router already applies the basename.
 */
export function appUrl(path: string): string {
  return `${getBasePath()}${path}`;
}

/**
 * Strip the base path from a window.location.pathname, yielding the
 * app-relative route ("/settings"). Pathnames outside the base path
 * are returned unchanged.
 */
export function stripBasePath(pathname: string): string {
  const base = getBasePath();
  if (!base) return pathname;
  if (pathname === base) return "/";
  if (pathname.startsWith(`${base}/`)) return pathname.slice(base.length);
  return pathname;
}
