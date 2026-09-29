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
