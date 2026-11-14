/*
 * What the FiestaBoard service worker may touch (web 2.8, WEB-16).
 * Pure functions, loaded by sw.js with importScripts and unit-tested in
 * web/src/__tests__/sw-shell-policy.test.ts.
 *
 * The one hard rule: nothing under the API is ever answered from, or written
 * to, a cache. API responses are per-account; the shell and hashed build
 * assets are the same for everyone.
 */
(function (root) {
  var SHELL_CACHE = 'fb-shell-v2';
  var ASSET_CACHE = 'fb-assets-v2';
  var MAX_ASSETS = 300;

  /** Path relative to the worker's scope ("" for the scope root), or null when outside it. */
  function scopedPath(pathname, scopePath) {
    if (pathname.indexOf(scopePath) !== 0) return null;
    return pathname.slice(scopePath.length);
  }

  /**
   * How to handle one request:
   *   'bypass'   - not ours: the browser goes to the network as if there were no worker.
   *   'navigate' - a page load: network first, the cached shell only when the network fails.
   *   'asset'    - a hashed build file or icon: cache first.
   */
  function classify(req) {
    if (req.method !== 'GET') return 'bypass';
    if (!req.sameOrigin) return 'bypass';
    if (req.hasAuthorization || req.cache === 'no-store') return 'bypass';
    var path = scopedPath(req.pathname, req.scopePath);
    if (path === null || path.indexOf('%') !== -1) return 'bypass';
    if (path === 'api' || path.indexOf('api/') === 0) return 'bypass';
    if (req.mode === 'navigate') return 'navigate';
    if (path.indexOf('assets/') === 0 || path.indexOf('icons/') === 0) return 'asset';
    return 'bypass';
  }

  /** May this response be written to a cache? */
  function isStorable(res) {
    if (!res || res.status !== 200) return false;
    if (res.type !== 'basic' || res.redirected) return false;
    var cc = (res.cacheControl || '').toLowerCase();
    if (cc.indexOf('no-store') !== -1 || cc.indexOf('private') !== -1) return false;
    return true;
  }

  /** May this navigation response become the offline shell? Only the SPA's HTML, never a redirect. */
  function isShell(res) {
    return isStorable(res) && !res.redirected && (res.contentType || '').indexOf('text/html') === 0;
  }

  /** The build files a shell page loads up front, so the shell can boot offline. */
  function shellAssets(html, scopeUrl) {
    var out = [];
    var re = /(?:href|src)="([^"]*?assets\/[^"]+)"/g;
    var m;
    while ((m = re.exec(html)) !== null) {
      try {
        var scope = new URL(scopeUrl);
        var parsed = new URL(m[1], scopeUrl);
        var path = scopedPath(parsed.pathname, scope.pathname);
        if (parsed.origin !== scope.origin || path === null || path.indexOf('%') !== -1 || path.indexOf('assets/') !== 0) continue;
        if (out.indexOf(parsed.href) === -1) out.push(parsed.href);
      } catch (e) { /* malformed references are not cache candidates */ }
    }
    return out;
  }

  /** Caches this worker owns, or older FiestaBoard workers left behind. */
  function isObsoleteCache(name, scope) {
    if (name === SHELL_CACHE || name === ASSET_CACHE) return false;
    if (name === 'offlineCache' || name.indexOf('fiestaboard-') === 0) return true;
    if (name.indexOf('fb-') === 0) return true;
    return name.indexOf('workbox-precache-') === 0 && name.slice(-scope.length) === scope;
  }

  root.fbShellPolicy = {
    SHELL_CACHE: SHELL_CACHE,
    ASSET_CACHE: ASSET_CACHE,
    MAX_ASSETS: MAX_ASSETS,
    classify: classify,
    isStorable: isStorable,
    isShell: isShell,
    shellAssets: shellAssets,
    isObsoleteCache: isObsoleteCache,
  };
})(self);
