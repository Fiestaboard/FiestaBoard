/* H15 push delivery. The app attention badge is owned by the navigation UI. */
(function () {
  'use strict';

  function safePath(value) {
    var path = value.split(/[?#]/)[0];
    // Check before URL() removes dot segments, including encoded separators and
    // nested encodings which an ingress proxy or router could decode again.
    for (var i = 0; i < 5; i++) {
      if (path.indexOf('\\') !== -1 || /(^|\/)\.{1,2}(\/|$)/.test(path) || path.indexOf('//') === 0) return false;
      if (path.indexOf('%') === -1) return true;
      try {
        var decoded = decodeURIComponent(path);
        if (decoded === path) return true;
        path = decoded;
      } catch (e) { return false; }
    }
    return false;
  }

  function scopedUrl(value, stored) {
    var scope = new URL(self.registration.scope);
    if (typeof value !== 'string' || value.length > 1024 + (stored ? scope.href.length : 0) || value.indexOf('\\') !== -1 || /[\x00-\x1f\x7f]/.test(value)) return scope.href;
    try {
      var target;
      if (/^[a-z][a-z\d+.-]*:/i.test(value)) {
        // Push payload URLs are hub-relative. Only our stored click data may
        // already be absolute, and it must still belong to this app scope.
        if (!stored) return scope.href;
        var path = value.replace(/^[a-z][a-z\d+.-]*:\/\/[^/]*/i, '');
        if (!safePath(path)) return scope.href;
        target = new URL(value);
      } else {
        if (!safePath(value)) return scope.href;
        var relative = value;
        if (relative.indexOf(scope.pathname) === 0) relative = relative.slice(scope.pathname.length);
        else if (relative.charAt(0) === '/') relative = relative.slice(1);
        target = new URL(relative, scope);
      }
      if (target.origin !== scope.origin || target.username || target.password || target.pathname.indexOf(scope.pathname) !== 0) return scope.href;
      return target.href;
    } catch (e) { return scope.href; }
  }

  function text(value, limit) {
    return typeof value === 'string' ? Array.from(value).slice(0, limit).join('') : '';
  }

  self.addEventListener('push', function (event) {
    event.waitUntil((async function () {
      var payload;
      try { payload = event.data && event.data.json(); } catch (e) { /* Never display or log raw payloads. */ }
      if (!payload || typeof payload !== 'object' || Array.isArray(payload)) payload = {};
      var title = text(payload.title, 80).trim() || 'FiestaBoard';
      var options = {
        body: text(payload.body, 240),
        data: { url: scopedUrl(payload.url, false) },
      };
      var tag = text(payload.tag, 64);
      if (tag) options.tag = tag;
      await self.registration.showNotification(title, options);
    })());
  });

  self.addEventListener('notificationclick', function (event) {
    event.notification.close();
    event.waitUntil((async function () {
      var url = scopedUrl(event.notification.data && event.notification.data.url, true);
      try {
        var windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
        for (var i = 0; i < windows.length; i++) {
          if (windows[i].url !== url) continue;
          try {
            await windows[i].focus();
            return;
          } catch (e) { /* The window may have closed since matchAll(). */ }
        }
      } catch (e) { /* Try a new window when client lookup is unavailable. */ }
      await self.clients.openWindow(url);
    })());
  });

  async function closeNotifications() {
    try {
      var notifications = await self.registration.getNotifications();
      notifications.forEach(function (notification) {
        try { notification.close(); } catch (e) { /* Continue closing the remaining notifications. */ }
      });
    } catch (e) { /* Notification cleanup is best effort. */ }
  }

  self.addEventListener('message', function (event) {
    var type = event.data && event.data.type;
    // The page owns More attention and clears its badge on sign-out. Push
    // cleanup must not acknowledge that independent attention state.
    if (type === 'CLEAR_PUSH') event.waitUntil(closeNotifications());
  });
})();
