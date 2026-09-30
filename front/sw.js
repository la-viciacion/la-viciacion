// Pass-through service worker.
//
// The app needs the API for everything, so caching the shell for offline use
// bought nothing and caused stale/corrupted-cache problems after deploys.
// This worker caches nothing: it only wipes the caches left behind by earlier
// versions and lets every request go straight to the network. The fetch
// handler is kept (and left empty) so browsers still treat the app as installable.

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.map((k) => caches.delete(k)))).then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', () => {});

// Web Push (server: api/src/utils/push.py). The payload is {title, body, url, tag}.
self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : '' };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || 'La Viciación', {
      body: data.body || '',
      icon: 'icon-192.png',
      badge: 'icon-64.png',
      tag: data.tag || undefined,
      renotify: Boolean(data.tag), // a newer notice with the same tag replaces the old one but still alerts
      data: { url: data.url || '/' },
    }),
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((open) => {
      const existing = open.find((client) => 'focus' in client);
      return existing ? existing.focus() : clients.openWindow(url);
    }),
  );
});
