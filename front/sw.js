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

// Web Push (server: api/src/utils/push.py). The payload is {title, body, url, tag, image?, quiet?, kind?}.
const ICONS = { icon: 'assets/icons/icon-192.png', badge: 'assets/icons/badge-96.png' };

// Mirror of push.elapsed_text (api/src/utils/push.py)
function formatElapsed(ms) {
  const total = Math.max(0, Math.floor(ms / 60000));
  if (total < 1) return 'Timer iniciado';
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  return hours ? `${hours}h ${String(minutes).padStart(2, '0')}min` : `${minutes} min`;
}

// The running-timer notification (kind "timer"): pinned, silent, refreshed by the server every
// 5 minutes under the same tag. `data` keeps what the buttons need: game, start (epoch ms), token
// (lets "Parar" stop this one timer without a session; see POST /push/stop-timer).
function timerNotification(data, body, buttons) {
  return self.registration.showNotification(data.game, {
    ...ICONS,
    body,
    tag: 'timer',
    silent: true,
    requireInteraction: true,
    actions: buttons,
    data,
  });
}

const showTimer = (data) =>
  timerNotification(data, formatElapsed(Date.now() - data.start), [{ action: 'stop', title: 'Parar' }]);

// "Parar" asks first: a pocket tap must not end a session. Both answers are buttons of this same
// notification, so nothing has to be fetched to show it.
const askToStop = (data) =>
  timerNotification(data, `¿Parar el timer? Llevas ${formatElapsed(Date.now() - data.start)}`, [
    { action: 'confirm-stop', title: 'Sí, parar' },
    { action: 'cancel', title: 'Cancelar' },
  ]);

function openApp(url) {
  return clients.matchAll({ type: 'window', includeUncontrolled: true }).then((open) => {
    const existing = open.find((client) => 'focus' in client);
    return existing ? existing.focus() : clients.openWindow(url);
  });
}

async function stopTimer(data) {
  try {
    const response = await fetch('/api/v1/push/stop-timer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: data.token }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
  } catch {
    // expired token or no network: the timer is still running, so leave its notification and let the app do it
    await showTimer(data);
    return openApp(data.url);
  }
  const elapsed = formatElapsed(Date.now() - data.start);
  return self.registration.showNotification(data.game, {
    ...ICONS,
    body: elapsed === 'Timer iniciado' ? 'Timer parado' : `Timer parado · ${elapsed}`,
    tag: 'timer',
    silent: true,
    data: { url: data.url },
  });
}

self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : '' };
  }
  if (data.kind === 'timer') {
    event.waitUntil(timerNotification({ url: data.url || '/', game: data.title, start: data.start, token: data.token, kind: 'timer' }, data.body || '', [{ action: 'stop', title: 'Parar' }]));
    return;
  }
  event.waitUntil(
    self.registration.showNotification(data.title || 'La Viciación', {
      ...ICONS,
      body: data.body || '',
      image: data.image || undefined, // large picture: Android and desktop only
      tag: data.tag || undefined,
      silent: Boolean(data.quiet), // quiet updates must not alert (Chrome rejects silent together with renotify)
      renotify: Boolean(data.tag) && !data.quiet, // a newer notice with the same tag replaces the old one but still alerts
      data: { url: data.url || '/' },
    }),
  );
});

self.addEventListener('notificationclick', (event) => {
  const data = event.notification.data || {};
  if (data.kind === 'timer') {
    if (event.action === 'stop') return event.waitUntil(askToStop(data));
    if (event.action === 'confirm-stop') return event.waitUntil(stopTimer(data));
    if (event.action === 'cancel') return event.waitUntil(showTimer(data));
  }
  event.notification.close();
  event.waitUntil(openApp(data.url || '/'));
});
