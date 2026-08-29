import { stripBasePath } from "./base-path";

/**
 * Routes that render without app chrome (sidebar, content padding, wizard
 * takeover, login redirects). `/login` owns its own auth UI; `/panel/:id`
 * (and its TV-typable alias `/p/:ref`) is the FiestaPanel viewer, which
 * must never grow chrome or bounce an unauthenticated TV browser to the
 * login form.
 */
const CHROMELESS_PREFIXES = ["/login", "/panel/", "/p/"] as const;

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
