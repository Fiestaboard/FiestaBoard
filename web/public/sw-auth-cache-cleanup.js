/* Keep old authenticated responses out of offline use after an upgrade. */
self.addEventListener('install', (event) => {
  event.waitUntil(self.skipWaiting());
});
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const scope = self.registration.scope;
    const names = await caches.keys();
    await Promise.all(names.filter((name) =>
      name === 'offlineCache' ||
      name.startsWith('fiestaboard-') ||
      (name.startsWith('workbox-precache-') && name.endsWith(scope))
    ).map((name) => caches.delete(name)));
    // Replace an older fetch handler for existing tabs, then remove this worker.
    // A controlled tab remains network-only until its next navigation.
    await self.clients.claim();
    await self.registration.unregister();
  })());
});
