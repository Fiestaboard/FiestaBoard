/**
 * What this browser can honestly do as an installed app (WEB-12, WEB-16).
 *
 * Service workers, `beforeinstallprompt` and offline all need a secure
 * context: https, or localhost. On a plain-http LAN address
 * (http://fiestapi.local) the browser hides its own Install button, so the
 * app must not draw one either (07 note `58:34443`, "No fake button").
 *
 * Every helper takes the window it reads, so tests pass a stub instead of
 * patching jsdom globals.
 */

type WindowLike = Pick<Window, "isSecureContext" | "matchMedia"> & {
  navigator: Pick<Navigator, "userAgent" | "maxTouchPoints"> & { standalone?: boolean };
};

/** True on https or localhost: the only places a service worker can run. */
export function isSecureOrigin(win: Pick<Window, "isSecureContext"> = window): boolean {
  return win.isSecureContext === true;
}

/** True when the app is already running as an installed app. */
export function isStandalone(win: WindowLike = window): boolean {
  if (win.navigator.standalone === true) return true;
  try {
    return win.matchMedia("(display-mode: standalone)").matches;
  } catch {
    return false;
  }
}

/**
 * True for Safari on iPhone and iPad, which never fires `beforeinstallprompt`
 * and installs only through Share › Add to Home Screen. iPadOS reports a Mac
 * user agent, so a Mac with touch points is an iPad. Chrome, Firefox and Edge
 * on iOS carry their own token and name their menus differently, so the
 * Safari steps would be wrong for them.
 */
export function isIosSafari(win: WindowLike = window): boolean {
  const ua = win.navigator.userAgent;
  const iosDevice = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && win.navigator.maxTouchPoints > 1);
  if (!iosDevice) return false;
  return /Safari\//.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS|GSA\//.test(ua);
}

/**
 * True for browsers that can install a web app once the page is secure:
 * Chromium-family browsers (Chrome, Edge, Samsung Internet, Opera, Android
 * WebView-based Chrome) and Safari on iOS. Firefox and desktop Safari can't
 * install from a page at all, so telling them "you need HTTPS to install"
 * would promise something HTTPS doesn't deliver.
 */
export function canInstallOnSecureOrigin(win: WindowLike = window): boolean {
  if (isIosSafari(win)) return true;
  const ua = win.navigator.userAgent;
  if (/Firefox\/|FxiOS|iPhone|iPad|iPod/.test(ua)) return false;
  return /(Chrome|Chromium|Edg|SamsungBrowser|OPR)\//.test(ua);
}
