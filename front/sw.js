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

// Web Push (server: api/src/utils/push.py). The payload is {title, body, url, tag, image?, quiet?, pinned?, button?}.
// `quiet` notices (the running-timer one, refreshed every 5 minutes under the same tag) must not
// alert; `pinned` ones stay on screen until tapped or replaced; `button` adds one action button
// (every tap, on it or on the notification, just opens `url`: the app does the work).
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
      icon: 'assets/icons/icon-192.png',
      badge: 'assets/icons/badge-96.png',
      image: data.image || undefined, // large picture: Android and desktop only
      tag: data.tag || undefined,
      silent: Boolean(data.quiet),
      renotify: Boolean(data.tag) && !data.quiet, // a newer notice with the same tag replaces the old one but still alerts (Chrome rejects renotify together with silent)
      requireInteraction: Boolean(data.pinned),
      actions: data.button ? [{ action: 'open', title: String(data.button) }] : undefined,
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
