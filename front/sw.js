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
// `quiet` notices (the running-timer one, refreshed every 10 minutes under the same tag) must not
// alert; `pinned` ones stay on screen, also after being tapped (see notificationclick); `button`
// adds one action button (every tap, on it or on the notification, just opens `url`: the app does the work).
const ICONS = { icon: 'assets/icons/icon-192.png', badge: 'assets/icons/badge-96.png' };

function noticeOptions(data) {
  return {
    ...ICONS,
    body: data.body || '',
    image: data.image || undefined, // large picture: Android and desktop only
    tag: data.tag || undefined,
    silent: Boolean(data.quiet),
    renotify: Boolean(data.tag) && !data.quiet, // a newer notice with the same tag replaces the old one but still alerts (Chrome rejects renotify together with silent)
    requireInteraction: Boolean(data.pinned),
    actions: data.button ? [{ action: 'open', title: String(data.button) }] : undefined,
    // what a re-show of this notification needs (the browser gives it back on click)
    data: { url: data.url || '/', body: data.body || '', tag: data.tag, quiet: Boolean(data.quiet), pinned: Boolean(data.pinned), button: data.button },
  };
}

self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : '' };
  }
  event.waitUntil(
    (async () => {
      if (data.quiet && data.tag) {
        // a quiet notice is a refresh of the previous one: iOS does not replace by tag, it piles them up
        for (const previous of await self.registration.getNotifications({ tag: data.tag })) previous.close();
      }
      await self.registration.showNotification(data.title || 'La Viciación', noticeOptions(data));
    })(),
  );
});

self.addEventListener('notificationclick', (event) => {
  const { title, data = {} } = event.notification;
  const url = data.url || '/';
  const opening = clients.matchAll({ type: 'window', includeUncontrolled: true }).then((open) => {
    const existing = open.find((client) => 'focus' in client);
    return existing ? existing.focus() : clients.openWindow(url);
  });
  if (data.pinned) {
    // the browser dismisses a notification when it (or its button) is tapped: a pinned one must outlive the tap,
    // so it is shown again under the same tag; the server replaces or removes it when the timer changes
    event.waitUntil(Promise.all([opening, self.registration.showNotification(title, noticeOptions(data))]));
    return;
  }
  event.notification.close();
  event.waitUntil(opening);
});
