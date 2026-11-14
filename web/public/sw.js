/*
 * FiestaBoard app-shell service worker (web 2.8, WEB-16).
 *
 * Registered only in a secure context (https or localhost); see
 * web/src/lib/pwa/register-service-worker.ts. What it does:
 *
 * - Page loads go to the network first. The last good copy of the SPA's
 *   anonymously fetched index.html is used only when the network fails, so an online tab always
 *   gets the current release and nobody is stranded on a stale shell.
 * - Hashed build files (assets/) and icons are cache-first: their names
 *   change with their content, so a cached copy is never stale.
 * - The API is never cached and never answered by this worker. Neither is
 *   anything sent with an Authorization header, marked no-store or private,
 *   cross-origin, or not a GET.
 * - On activate it deletes the caches of older FiestaBoard workers.
 */
importScripts('./sw-shell-policy.js');

var P = self.fbShellPolicy;

function scopeUrl() {
  return self.registration.scope;
}

function shellKey() {
  return new Request(scopeUrl());
}

function describe(response) {
  return {
    status: response.status,
    type: response.type,
    redirected: response.redirected,
    cacheControl: response.headers.get('cache-control'),
    contentType: response.headers.get('content-type'),
  };
}

async function trimAssets(cache) {
  var keys = await cache.keys();
  var extra = keys.length - P.MAX_ASSETS;
  for (var i = 0; i < extra; i++) await cache.delete(keys[i]);
}

async function cacheShellAssets(html) {
  var cache = await caches.open(P.ASSET_CACHE);
  var urls = P.shellAssets(html, scopeUrl());
  await Promise.all(
    urls.map(async function (url) {
      if (await cache.match(url)) return;
      try {
        var res = await fetch(url, { credentials: 'omit' });
        if (P.isStorable(describe(res))) await cache.put(url, res);
      } catch (e) {
        /* offline or gone: the next page load tries again */
      }
    }),
  );
  await trimAssets(cache);
}

async function storeShell(response) {
  var html = await response.clone().text();
  var cache = await caches.open(P.SHELL_CACHE);
  await cache.put(shellKey(), response);
  await cacheShellAssets(html);
}

async function refreshShell() {
  try {
    var res = await fetch(scopeUrl(), { credentials: 'omit', cache: 'no-store' });
    if (P.isShell(describe(res))) await storeShell(res);
  } catch (e) {
    /* first install while offline: nothing to keep yet */
  }
}

async function navigate(event) {
  try {
    var res = await fetch(event.request);
    // Never persist a credentialed navigation response (including sign-in pages).
    event.waitUntil(refreshShell());
    return res;
  } catch (err) {
    var cached = await caches.match(shellKey(), { cacheName: P.SHELL_CACHE });
    if (cached) return cached;
    throw err;
  }
}

async function cacheAnonymousAsset(url) {
  try {
    // A fresh URL request carries none of the caller's cookies or custom headers.
    var res = await fetch(url, { credentials: 'omit', cache: 'no-store' });
    if (!P.isStorable(describe(res))) return;
    var cache = await caches.open(P.ASSET_CACHE);
    await cache.put(url, res);
    await trimAssets(cache);
  } catch (e) { /* Cache population is best-effort, never required for online delivery. */ }
}

async function asset(event) {
  var request = event.request;
  try {
    var cache = await caches.open(P.ASSET_CACHE);
    var hit = await cache.match(request);
    if (hit) return hit;
  } catch (e) { /* Unavailable storage must fall through to the original network request. */ }
  var res = await fetch(request);
  // Keep online authentication intact; only a separate anonymous response may be stored.
  event.waitUntil(cacheAnonymousAsset(request.url));
  return res;
}

self.addEventListener('install', function (event) {
  // Nothing here is versioned per release (no precache list), so a new
  // worker can take over at once; page loads stay network-first either way.
  event.waitUntil(refreshShell().then(function () { return self.skipWaiting(); }));
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    (async function () {
      var scope = scopeUrl();
      var names = await caches.keys();
      await Promise.all(
        names.filter(function (name) { return P.isObsoleteCache(name, scope); }).map(function (name) {
          return caches.delete(name);
        }),
      );
      await self.clients.claim();
    })(),
  );
});

self.addEventListener('fetch', function (event) {
  var request = event.request;
  var url = new URL(request.url);
  var kind = P.classify({
    method: request.method,
    cache: request.cache,
    mode: request.mode,
    sameOrigin: url.origin === self.location.origin,
    hasAuthorization: request.headers.has('authorization'),
    pathname: url.pathname,
    scopePath: new URL(scopeUrl()).pathname,
  });
  if (kind === 'navigate') event.respondWith(navigate(event));
  else if (kind === 'asset') event.respondWith(asset(event));
  // 'bypass': no respondWith, so the browser handles it as if there were no worker.
});
