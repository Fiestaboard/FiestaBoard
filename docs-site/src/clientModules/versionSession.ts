/**
 * Docusaurus client module: session-scoped docs version preference.
 *
 * Docusaurus persists the user's last-selected docs version in localStorage
 * (`docs-preferred-version-default`). That means a user who once picked an
 * old version will keep seeing it on every future visit - even after months.
 *
 * Desired behaviour:
 *   • Loading the docs without a version in the URL → always land on the
 *     latest version (unless the user picks a different one this session).
 *   • User selects a version from the dropdown → remember it for the rest
 *     of the current browser session.
 *   • New session (tab/window opened fresh) → back to the latest version.
 *
 * How it works:
 *   1. On first page load of a new session (sessionStorage is empty):
 *      remove the localStorage entry so Docusaurus falls back to its default
 *      (the latest versioned release).
 *   2. On subsequent page loads within the same session, restore the
 *      sessionStorage value into localStorage before Docusaurus reads it.
 *   3. After every route update (including version-dropdown navigation),
 *      read whatever Docusaurus wrote to localStorage and mirror it into
 *      sessionStorage so the choice survives in-session navigations.
 */

const DOCUSAURUS_LS_KEY = "docs-preferred-version-default";
const SESSION_KEY = "fiestaboard-docs-preferred-version";

if (typeof window !== "undefined") {
  const savedVersion = sessionStorage.getItem(SESSION_KEY);

  if (savedVersion === null) {
    // New session: clear any stale persistent preference so Docusaurus
    // falls back to the latest published version.
    localStorage.removeItem(DOCUSAURUS_LS_KEY);
  } else {
    // Continuing session: restore the user's in-session choice.
    localStorage.setItem(DOCUSAURUS_LS_KEY, savedVersion);
  }
}

/**
 * Called by Docusaurus after every client-side navigation.
 * Sync whatever version Docusaurus stored (e.g. after the user picked one
 * from the dropdown) back into sessionStorage.
 */
export function onRouteDidUpdate(): void {
  if (typeof window === "undefined") return;
  const currentVersion = localStorage.getItem(DOCUSAURUS_LS_KEY);
  if (currentVersion !== null) {
    sessionStorage.setItem(SESSION_KEY, currentVersion);
  }
}
