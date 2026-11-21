import { stripBasePath } from "./base-path";

/**
 * Routes that render without app chrome (sidebar, content padding, wizard
 * takeover, login redirects). `/login` owns its own auth UI; `/panel/:id`
 * (and its TV-typable alias `/p/:ref`) is the FiestaPanel viewer, which
 * must never grow chrome or bounce an unauthenticated TV browser to the
 * login form.
 */
const CHROMELESS_PREFIXES = ["/activate", "/reset-password", "/login", "/panel/", "/p/"] as const;

function normalize(pathname: string): string {
  const stripped = stripBasePath(pathname);
  const queryIndex = stripped.indexOf("?");
  return queryIndex === -1 ? stripped : stripped.slice(0, queryIndex);
}

/** True on the FiestaPanel viewer routes (`/panel/:panelId`, `/p/:ref`). */
export function isPanelPath(pathname: string): boolean {
  const path = normalize(pathname);
  return path.startsWith("/panel/") || path.startsWith("/p/");
}

/** True on any route that renders without the app chrome. */
export function isChromelessPath(pathname: string): boolean {
  const path = normalize(pathname);
  return CHROMELESS_PREFIXES.some((prefix) => path === prefix || path.startsWith(prefix));
}

/**
 * True on the page editor (`/pages/new`, `/pages/edit/:id`, `/pages/edit?id=`).
 * Below the rail its own toolbar replaces the phone nav (Figma 57:64661), so
 * the shell draws no tab bar or phone header there (BB-B-17).
 */
export function isPageEditorPath(pathname: string): boolean {
  const path = normalize(pathname);
  // One id segment only: a deeper path is the not-found page, which keeps the nav.
  return path === "/pages/new" || path === "/pages/edit" || /^\/pages\/edit\/[^/]+\/?$/.test(path);
}
